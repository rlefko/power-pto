import { useRouteError, isRouteErrorResponse } from "react-router";
import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";

export function ErrorFallback() {
  const error = useRouteError();
  const isNotFound = isRouteErrorResponse(error) && error.status === 404;

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 p-8">
      <AlertCircle className="h-12 w-12 text-muted-foreground" />
      <h1 className="text-2xl font-semibold">{isNotFound ? "Page Not Found" : "Something went wrong"}</h1>
      <p className="max-w-md text-center text-muted-foreground">
        {isNotFound
          ? "The page you're looking for doesn't exist."
          : "An unexpected error occurred. Please try reloading the page."}
      </p>
      <Button onClick={() => window.location.reload()}>Reload</Button>
    </div>
  );
}
