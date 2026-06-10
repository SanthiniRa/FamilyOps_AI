"use client";

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import AuthLayout from "@/components/auth/auth-layout";
import { useAuth } from "@/components/auth/auth-provider";
import { AlertCircle, LockKeyhole, Mail } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const loginMutation = useMutation({
    mutationFn: async () => {
      const response = await authApi.login({ email, password });
      return response.data;
    },
    onSuccess: (data) => {
      setErrorMessage("");
      setSession(data.access_token, data.user);
      router.push("/");
    },
    onError: (error: any) => {
      setErrorMessage(
        error?.response?.data?.detail ||
          error?.message ||
          "Could not sign in. Please check your credentials."
      );
    },
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email || !password) {
      setErrorMessage("Please enter your email and password.");
      return;
    }
    loginMutation.mutate();
  };

  return (
    <AuthLayout
      eyebrow="FamilyOps AI"
      title="Welcome back."
      description="Sign in to your household workspace and pick up where your agents, tasks, and family data left off."
      footerLink={{
        label: "Need an account?",
        href: "/register",
        text: "Create one",
      }}
    >
      <form className="space-y-5" onSubmit={onSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Email</label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              className="pl-10"
              autoComplete="email"
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Password</label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              className="pl-10"
              autoComplete="current-password"
            />
          </div>
        </div>

        {errorMessage && (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        <Button type="submit" className="w-full" disabled={loginMutation.isPending}>
          {loginMutation.isPending ? "Signing in..." : "Sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}
