const chromeUrl = "http://127.0.0.1:9223";
const appUrl = "http://127.0.0.1:5173/chat";

async function getWebSocketUrl() {
  const target = await fetch(`${chromeUrl}/json/new?${encodeURIComponent("about:blank")}`, {
    method: "PUT",
  }).then((res) => res.json());
  return target.webSocketDebuggerUrl;
}

function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let nextId = 1;
  const pending = new Map();
  const events = [];

  ws.onmessage = (message) => {
    const data = JSON.parse(message.data);
    if (data.id && pending.has(data.id)) {
      pending.get(data.id)(data);
      pending.delete(data.id);
    } else if (data.method) {
      events.push(data);
    }
  };

  const send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, (data) => {
        if (data.error) reject(new Error(`${method}: ${JSON.stringify(data.error)}`));
        else resolve(data.result);
      });
      ws.send(JSON.stringify({ id, method, params }));
    });

  const waitForEvent = (method, timeoutMs = 30000) =>
    new Promise((resolve, reject) => {
      const started = Date.now();
      const timer = setInterval(() => {
        const index = events.findIndex((event) => event.method === method);
        if (index >= 0) {
          clearInterval(timer);
          resolve(events.splice(index, 1)[0]);
        } else if (Date.now() - started > timeoutMs) {
          clearInterval(timer);
          reject(new Error(`Timed out waiting for ${method}`));
        }
      }, 50);
    });

  return new Promise((resolve) => {
    ws.onopen = () => resolve({ send, waitForEvent, close: () => ws.close() });
  });
}

async function evaluate(cdp, expression, timeoutMs = 30000) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    timeout: timeoutMs,
  });
  if (result.exceptionDetails) {
    throw new Error(JSON.stringify(result.exceptionDetails));
  }
  return result.result?.value;
}

const cdp = await connect(await getWebSocketUrl());
try {
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Browser.grantPermissions", {
    origin: "http://127.0.0.1:5173",
    permissions: ["geolocation"],
  });
  await cdp.send("Emulation.setGeolocationOverride", {
    latitude: 12.9715,
    longitude: 80.043,
    accuracy: 10,
  });
  await cdp.send("Page.navigate", { url: appUrl });
  await cdp.waitForEvent("Page.loadEventFired");

  await evaluate(
    cdp,
    `new Promise((resolve, reject) => {
      const started = Date.now();
      const timer = setInterval(() => {
        const textarea = document.querySelector("textarea");
        if (textarea) {
          clearInterval(timer);
          resolve(true);
        } else if (Date.now() - started > 30000) {
          clearInterval(timer);
          reject(new Error("textarea not found"));
        }
      }, 100);
    })`,
  );

  const rect = await evaluate(
    cdp,
    `(() => {
      const textarea = document.querySelector("textarea");
      if (!textarea) throw new Error("textarea not found");
      const rect = textarea.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    })()`,
  );
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: rect.x,
    y: rect.y,
    button: "left",
    clickCount: 1,
  });
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: rect.x,
    y: rect.y,
    button: "left",
    clickCount: 1,
  });
  for (const char of "tell the top 2 hospital in my location") {
    await cdp.send("Input.dispatchKeyEvent", {
      type: "keyDown",
      text: char,
      unmodifiedText: char,
      key: char === " " ? " " : char,
      windowsVirtualKeyCode: char.toUpperCase().charCodeAt(0),
    });
    await cdp.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: char === " " ? " " : char,
      windowsVirtualKeyCode: char.toUpperCase().charCodeAt(0),
    });
  }
  const valueAfterType = await evaluate(cdp, `document.querySelector("textarea").value`);
  console.log("textarea:", valueAfterType);
  const buttonRect = await evaluate(
    cdp,
    `new Promise((resolve, reject) => {
      setTimeout(() => {
        const button = document.querySelector("button[type='submit']");
        if (!button) {
          reject(new Error("submit button not found"));
          return;
        }
        if (button.disabled) {
          reject(new Error("submit button disabled"));
          return;
        }
        const rect = button.getBoundingClientRect();
        resolve({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
      }, 250);
    })`,
  );
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: buttonRect.x,
    y: buttonRect.y,
    button: "left",
    clickCount: 1,
  });
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: buttonRect.x,
    y: buttonRect.y,
    button: "left",
    clickCount: 1,
  });

  const visibleText = await evaluate(
    cdp,
    `new Promise((resolve, reject) => {
      const started = Date.now();
      const timer = setInterval(() => {
        const text = document.body.innerText;
        if (text.includes("Mode: hospital") && /V\\.S\\. HOSPITAL|RAMANA EYE CENTRE|hospital/i.test(text)) {
          clearInterval(timer);
          resolve(text);
        } else if (Date.now() - started > 120000) {
          clearInterval(timer);
          reject(new Error(text));
        }
      }, 500);
    })`,
    125000,
  );

  console.log(visibleText);
} finally {
  cdp.close();
}
