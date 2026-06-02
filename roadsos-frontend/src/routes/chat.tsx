import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Send, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type ChatMessage } from "@/lib/api";
import { getLocation } from "@/lib/location";

export const Route = createFileRoute("/chat")({ component: Chat });

function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", content: "Hi, I'm RoadSoS AI. Ask me about safety, first-aid, or danger zones." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  useEffect(() => {
    getLocation().then(setCoords);
  }, []);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await api.chat(next, coords);
      setMessages([...next, { role: "assistant", content: res.reply }]);
    } catch {
      setMessages([
        ...next,
        {
          role: "assistant",
          content: "I could not reach the RoadSoS backend. Please make sure the backend is running on port 8000.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full min-h-0 max-w-3xl mx-auto p-4 md:p-8 flex flex-col overflow-hidden">
      <div className="mb-4 shrink-0">
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-primary" /> AI Safety Assistant
        </h1>
        <p className="text-sm text-muted-foreground">Powered by Gemini + RAG over road safety knowledge base.</p>
      </div>
      <Card className="flex-1 min-h-0 flex flex-col p-0 overflow-hidden">
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm ${
                  m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {busy && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-2xl bg-muted px-4 py-2.5 text-sm text-muted-foreground">
                Thinking…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        <div className="shrink-0 border-t border-border p-3 flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask about an accident, hospital, first-aid…"
          />
          <Button onClick={send} disabled={busy}><Send className="h-4 w-4" /></Button>
        </div>
      </Card>
    </div>
  );
}
