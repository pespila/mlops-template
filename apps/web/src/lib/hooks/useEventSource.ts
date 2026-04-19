import { useEffect, useRef, useState } from "react";

export type EventSourceState =
  | "idle"
  | "connecting"
  | "live"
  | "reconnecting"
  | "closed";

export interface UseEventSourceOptions<T> {
  url: string;
  /** Named events to listen for. Each event payload is JSON parsed to T. */
  events: readonly string[];
  enabled?: boolean;
  onEvent?: (name: string, data: T) => void;
}

export interface UseEventSourceResult {
  connectionState: EventSourceState;
  close: () => void;
}

const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

/**
 * Typed wrapper around the native EventSource API with automatic
 * reconnection + exponential backoff.
 */
export function useEventSource<T>({
  url,
  events,
  enabled = true,
  onEvent,
}: UseEventSourceOptions<T>): UseEventSourceResult {
  const [state, setState] = useState<EventSourceState>("idle");
  const sourceRef = useRef<EventSource | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByUserRef = useRef<boolean>(false);
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!enabled) {
      setState("idle");
      return;
    }

    closedByUserRef.current = false;

    function connect() {
      setState((prev) => (prev === "closed" ? "reconnecting" : "connecting"));
      const source = new EventSource(url, { withCredentials: true });
      sourceRef.current = source;

      source.onopen = () => {
        backoffRef.current = INITIAL_BACKOFF_MS;
        setState("live");
      };

      const listener = (ev: MessageEvent) => {
        try {
          const parsed = JSON.parse(ev.data) as T;
          onEventRef.current?.(ev.type, parsed);
        } catch {
          /* ignore non-JSON payloads */
        }
      };

      for (const name of events) {
        source.addEventListener(name, listener as EventListener);
      }
      source.addEventListener("message", listener as EventListener);

      source.onerror = () => {
        source.close();
        sourceRef.current = null;
        if (closedByUserRef.current) {
          setState("closed");
          return;
        }
        setState("reconnecting");
        const next = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        const delay = backoffRef.current;
        backoffRef.current = next;
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      closedByUserRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
      setState("closed");
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, enabled, events.join("|")]);

  return {
    connectionState: state,
    close: () => {
      closedByUserRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
      setState("closed");
    },
  };
}
