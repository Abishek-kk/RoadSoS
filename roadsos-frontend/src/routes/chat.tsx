import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Copy, LoaderCircle, MapPin, RotateCcw, Send, Sparkles, Trash2, User } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { api, apiErrorMessage, type ChatMessage } from "@/lib/api";
import { getLocation } from "@/lib/location";

export const Route = createFileRoute("/chat")({ component: Chat });

type UiMessage = ChatMessage & {
  id: string;
  intent?: string;
  usedLlm?: boolean;
  suggestions?: string[];
  error?: boolean;
};

const STARTER_PROMPTS = [
  "I had a road accident. What should I do first?",
  "Find nearby hospitals",
  "My vehicle broke down on the highway",
  "How do I stop heavy bleeding?",
];

function Chat() {
  const initialMessage = useMemo<UiMessage>(
    () => ({
      id: "welcome",
      role: "assistant",
      content:
        "Hi, I am RoadSoS AI. Tell me what happened and I will help with emergency steps, nearby services, and safer next actions.",
      suggestions: STARTER_PROMPTS.slice(0, 3),
    }),
    [],
  );
  const [messages, setMessages] = useState<UiMessage[]>([initialMessage]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locationReady, setLocationReady] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const activeSuggestions = latestAssistant?.suggestions?.filter(Boolean).slice(0, 3) ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    getLocation()
      .then((position) => {
        setCoords(position);
        setLocationReady(true);
      })
      .catch(() => setLocationReady(false));
  }, []);

  const resolveCoords = async () => {
    if (coords) return coords;
    try {
      const currentCoords = await getLocation();
      setCoords(currentCoords);
      setLocationReady(true);
      return currentCoords;
    } catch {
      setLocationReady(false);
      return null;
    }
  };

  const askAssistant = async (nextMessages: UiMessage[]) => {
    setBusy(true);
    try {
      const currentCoords = await resolveCoords();
      const payloadMessages = nextMessages.map(({ role, content }) => ({ role, content }));
      const res = await api.chat(payloadMessages, currentCoords);
      setMessages([
        ...nextMessages,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.reply,
          intent: res.intent,
          usedLlm: res.used_llm,
          suggestions: res.suggestions,
        },
      ]);
    } catch (error) {
      setMessages([
        ...nextMessages,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: apiErrorMessage(error),
          error: true,
          suggestions: ["Try again", "Find nearby hospitals", "What to do in an accident?"],
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const send = (textOverride?: string, baseMessages = messages) => {
    const text = (textOverride ?? input).trim();
    if (!text || busy) return;

    const nextMessages: UiMessage[] = [
      ...baseMessages,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
      },
    ];
    setMessages(nextMessages);
    setInput("");
    void askAssistant(nextMessages);
  };

  const retryLast = () => {
    if (busy) return;
    const lastUserIndex = messages.map((message) => message.role).lastIndexOf("user");
    if (lastUserIndex < 0) return;
    const lastUser = messages[lastUserIndex];
    send(lastUser.content, messages.slice(0, lastUserIndex));
  };

  const copyMessage = async (content: string) => {
    await navigator.clipboard?.writeText(content);
  };

  const resetChat = () => {
    if (busy) return;
    setMessages([initialMessage]);
    setInput("");
  };

  return (
    <TooltipProvider>
      <div className="h-full min-h-0 max-w-4xl mx-auto p-4 md:p-8 flex flex-col overflow-hidden">
        <div className="mb-4 flex shrink-0 items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight flex items-center gap-2">
              <Sparkles className="h-6 w-6 text-primary" /> RoadSoS AI
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" />
                {locationReady ? "Location active" : "Location optional"}
              </span>
              {latestAssistant?.intent && <span>Mode: {latestAssistant.intent}</span>}
              {latestAssistant?.usedLlm !== undefined && (
                <span>{latestAssistant.usedLlm ? "Gemini response" : "RoadSoS offline response"}</span>
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="outline" size="icon" onClick={retryLast} disabled={busy}>
                  <RotateCcw className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Retry last message</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="outline" size="icon" onClick={resetChat} disabled={busy}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Clear chat</TooltipContent>
            </Tooltip>
          </div>
        </div>

        <Card className="flex-1 min-h-0 flex flex-col p-0 overflow-hidden">
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 md:p-5 space-y-4">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} onCopy={copyMessage} />
            ))}

            {busy && (
              <div className="flex justify-start">
                <div className="flex max-w-[88%] items-start gap-3 rounded-2xl bg-muted px-4 py-3 text-sm text-muted-foreground">
                  <Bot className="mt-0.5 h-4 w-4 shrink-0" />
                  <span className="inline-flex items-center gap-2">
                    <LoaderCircle className="h-4 w-4 animate-spin" />
                    Thinking through the safest answer...
                  </span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {!busy && activeSuggestions.length > 0 && (
            <div className="border-t border-border px-3 py-3">
              <div className="flex gap-2 overflow-x-auto pb-1">
                {activeSuggestions.map((suggestion) => (
                  <Button
                    key={suggestion}
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="h-auto shrink-0 whitespace-normal rounded-full px-3 py-2 text-left text-xs"
                    onClick={() => send(suggestion)}
                  >
                    {suggestion}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <form
            className="shrink-0 border-t border-border p-3"
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
          >
            <div className="flex items-end gap-2">
              <Textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    send();
                  }
                }}
                placeholder="Ask RoadSoS AI..."
                className="max-h-36 min-h-[52px] resize-none"
                rows={2}
                disabled={busy}
              />
              <Button type="submit" size="icon" disabled={busy || !input.trim()} className="h-[52px] w-[52px] shrink-0">
                {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </TooltipProvider>
  );
}

function MessageBubble({ message, onCopy }: { message: UiMessage; onCopy: (content: string) => void }) {
  const isUser = message.role === "user";

  return (
    <div className={`group flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`flex max-w-[90%] gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
        <div
          className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
            isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
          }`}
        >
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>
        <div className="min-w-0">
          <div
            className={`whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              isUser
                ? "bg-primary text-primary-foreground"
                : message.error
                  ? "bg-destructive/10 text-destructive"
                  : "bg-muted text-foreground"
            }`}
          >
            {message.content}
          </div>
          {!isUser && (
            <div className="mt-1 flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs text-muted-foreground"
                onClick={() => onCopy(message.content)}
              >
                <Copy className="mr-1 h-3.5 w-3.5" />
                Copy
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
