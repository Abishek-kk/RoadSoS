import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Phone, Plus, Trash2, User } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Contact } from "@/lib/api";
import { toast } from "sonner";

export const Route = createFileRoute("/contacts")({ component: Contacts });

function Contacts() {
  const [list, setList] = useState<Contact[]>([
    { id: "1", name: "Mom", phone: "+91 98439 47069", relation: "Family" },
    { id: "2", name: "Dad", phone: "+91 73056 47064", relation: "Family" },
  ]);
  const [form, setForm] = useState({ name: "", phone: "", relation: "" });

  useEffect(() => { api.contacts().then(setList); }, []);

  const add = async () => {
    if (!form.name || !form.phone) return toast.error("Name and phone required");
    const c = await api.addContact(form);
    setList((l) => [...l, c]);
    setForm({ name: "", phone: "", relation: "" });
    toast.success("Contact added");
  };

  return (
    <div className="p-4 md:p-8 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Emergency Contacts</h1>
        <p className="text-sm text-muted-foreground">Automatically notified when you trigger SOS.</p>
      </div>

      <Card className="p-5 space-y-3">
        <div className="font-semibold">Add new contact</div>
        <div className="grid sm:grid-cols-3 gap-3">
          <div>
            <Label className="text-xs">Name</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div>
            <Label className="text-xs">Phone</Label>
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </div>
          <div>
            <Label className="text-xs">Relation</Label>
            <Input value={form.relation} onChange={(e) => setForm({ ...form, relation: e.target.value })} placeholder="Family, Friend…" />
          </div>
        </div>
        <Button onClick={add}><Plus className="h-4 w-4 mr-1" /> Add Contact</Button>
      </Card>

      <div className="grid sm:grid-cols-2 gap-3">
        {list.map((c) => (
          <Card key={c.id} className="p-4 flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/15 text-primary flex items-center justify-center">
              <User className="h-5 w-5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold truncate">{c.name}</div>
              <div className="text-xs text-muted-foreground flex items-center gap-1">
                <Phone className="h-3 w-3" /> {c.phone} {c.relation && `· ${c.relation}`}
              </div>
            </div>
            <Button size="icon" variant="ghost" onClick={() => setList((l) => l.filter((x) => x.id !== c.id))}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </Card>
        ))}
      </div>
    </div>
  );
}
