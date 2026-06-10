"use client";

import { useState, type FormEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import AuthLayout from "@/components/auth/auth-layout";
import { useAuth } from "@/components/auth/auth-provider";
import { AlertCircle, LockKeyhole, Mail, User } from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const registerMutation = useMutation({
    mutationFn: async () => {
      const response = await authApi.register({
        email,
        password,
        full_name: fullName || null,
      });
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
          "Could not create your account."
      );
    },
  });

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email || !password || !confirmPassword) {
      setErrorMessage("Please complete all required fields.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }
    registerMutation.mutate();
  };

  return (
    <AuthLayout
      eyebrow="FamilyOps AI"
      title="Create your household workspace."
      description="Set up your account and start using the household assistant with a real user session, not a shared token."
      footerLink={{
        label: "Already have an account?",
        href: "/login",
        text: "Sign in",
      }}
    >
      <form className="space-y-5" onSubmit={onSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Full name</label>
          <div className="relative">
            <User className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Alex Johnson"
              className="pl-10"
              autoComplete="name"
            />
          </div>
        </div>

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
              placeholder="At least 8 characters"
              className="pl-10"
              autoComplete="new-password"
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Confirm password</label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Repeat your password"
              className="pl-10"
              autoComplete="new-password"
            />
          </div>
        </div>

        {errorMessage && (
          <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        <Button type="submit" className="w-full" disabled={registerMutation.isPending}>
          {registerMutation.isPending ? "Creating account..." : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
