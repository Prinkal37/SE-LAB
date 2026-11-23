"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, session } from "@/lib/api";

// Login / register page (FR-4.1.1)
export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      if (mode === "register") await api.register(email, password);
      const { user } = await api.login(email, password);
      session.save(user);
      router.push("/courses");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <form onSubmit={submit} className="card mx-auto mt-10 max-w-sm space-y-3">
      <h1 className="text-xl font-bold">{mode === "login" ? "Login" : "Register as instructor"}</h1>
      <input className="input w-full" type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      <input className="input w-full" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button className="btn w-full" type="submit">{mode === "login" ? "Login" : "Register"}</button>
      <button type="button" className="text-sm underline" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Need an account? Register" : "Already have an account? Login"}
      </button>
    </form>
  );
}
