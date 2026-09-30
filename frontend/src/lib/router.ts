import { useEffect, useState } from "react";

export type Route =
  | { page: "projects" }
  | { page: "studio"; projectId: string | null }
  | { page: "voices" }
  | { page: "transcription" }
  | { page: "models" }
  | { page: "jobs" }
  | { page: "settings" };

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  switch (parts[0]) {
    case "studio":
      return { page: "studio", projectId: parts[1] ?? null };
    case "voices":
      return { page: "voices" };
    case "transcription":
      return { page: "transcription" };
    case "models":
      return { page: "models" };
    case "jobs":
      return { page: "jobs" };
    case "settings":
      return { page: "settings" };
    default:
      return { page: "projects" };
  }
}

export function navigate(path: string): void {
  window.location.hash = path.startsWith("#") ? path : `#${path}`;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}
