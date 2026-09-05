"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const hasSession = window.localStorage.getItem("alphapilot_token");
    router.replace(hasSession ? "/dashboard" : "/login");
  }, [router]);
  return null;
}
