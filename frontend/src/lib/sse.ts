/**
 * A thin EventSource wrapper.
 *
 * The browser reconnects automatically on a dropped connection, but it does
 * not give up on a server that is not there. This adds a failure counter so
 * the caller can stop trying and fall back to polling.
 */

export interface SseHandle {
  close(): void;
}

export interface SseOptions<T> {
  url: string;
  onMessage: (data: T) => void;
  /** Called once, after `maxFailures` consecutive errors. */
  onGiveUp: () => void;
  maxFailures?: number;
}

export function subscribe<T>({
  url,
  onMessage,
  onGiveUp,
  maxFailures = 2,
}: SseOptions<T>): SseHandle {
  if (typeof EventSource === "undefined") {
    onGiveUp();
    return { close() {} };
  }

  let failures = 0;
  let closed = false;
  const source = new EventSource(url);

  source.onmessage = (event) => {
    failures = 0;
    try {
      onMessage(JSON.parse(event.data) as T);
    } catch {
      /* a malformed frame is not worth tearing the stream down for */
    }
  };

  source.onerror = () => {
    failures += 1;
    if (failures >= maxFailures && !closed) {
      closed = true;
      source.close();
      onGiveUp();
    }
  };

  return {
    close() {
      closed = true;
      source.close();
    },
  };
}
