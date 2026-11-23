"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { session } from "@/lib/api";
import type { User } from "@/lib/types";

// Returns the logged-in user. If nobody is logged in, goes back to the login page.
export function useUser() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    const u = session.get();
    if (!u) router.push("/");
    else setUser(u);
  }, [router]);
  return user;
}
