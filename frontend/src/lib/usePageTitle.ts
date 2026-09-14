import { useEffect } from "react";

/** MUST: <title> matches current context (Web Interface Guidelines). Cheap
 * enough that every page sets its own rather than leaving index.html's
 * static "CartPace" for the whole session. */
export function usePageTitle(title: string) {
  useEffect(() => {
    const prev = document.title;
    document.title = `${title} — CartPace`;
    return () => {
      document.title = prev;
    };
  }, [title]);
}
