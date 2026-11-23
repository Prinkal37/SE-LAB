"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { session } from "@/lib/api";
import type { User } from "@/lib/types";

export default function Header() {
  const [user, setUser] = useState<User | null>(null);
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    setUser(session.get());
  }, [path]);

  function logout() {
    session.clear();
    setUser(null);
    router.push("/");
  }

  return (
    <header className="flex items-center justify-between bg-blue-900 px-4 py-2 text-white">
      <Link href={user ? "/courses" : "/"} className="font-bold">Adaptive Viva Generator</Link>
      {user && (
        <div className="text-sm">
          {user.email} ({user.role})
          <button className="ml-3 underline" onClick={logout}>Logout</button>
        </div>
      )}
    </header>
  );
}
