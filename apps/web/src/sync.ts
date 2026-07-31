export type SyncTopic = "connections" | "live";

interface SyncMessage {
  id: string;
  topic: SyncTopic;
  sent_at: number;
  tab_id: string;
}

const CHANNEL_NAME = "capexgraph-local-sync";
const STORAGE_KEY = "capexgraph:local-sync";
const EVENT_NAME = "capexgraph:local-sync";
const TAB_ID =
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

let publisher: BroadcastChannel | null = null;

function publisherChannel(): BroadcastChannel | null {
  if (typeof BroadcastChannel === "undefined") return null;
  publisher ??= new BroadcastChannel(CHANNEL_NAME);
  return publisher;
}

export function publishSync(topic: SyncTopic): void {
  const message: SyncMessage = {
    id:
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    topic,
    sent_at: Date.now(),
    tab_id: TAB_ID,
  };
  window.dispatchEvent(new CustomEvent<SyncMessage>(EVENT_NAME, { detail: message }));
  publisherChannel()?.postMessage(message);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(message));
  } catch {
    // BroadcastChannel and the in-tab event remain available when storage is blocked.
  }
}

export function subscribeSync(
  topics: SyncTopic | SyncTopic[],
  callback: (topic: SyncTopic) => void,
  options: { remoteOnly?: boolean } = {},
): () => void {
  const accepted = new Set(Array.isArray(topics) ? topics : [topics]);
  const seen = new Set<string>();
  const handle = (message: SyncMessage) => {
    if (
      !message
      || !accepted.has(message.topic)
      || (options.remoteOnly && message.tab_id === TAB_ID)
      || seen.has(message.id)
    ) return;
    seen.add(message.id);
    if (seen.size > 100) {
      const oldest = seen.values().next().value;
      if (oldest) seen.delete(oldest);
    }
    callback(message.topic);
  };
  const handleLocal = (event: Event) => {
    handle((event as CustomEvent<SyncMessage>).detail);
  };
  const handleStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY || !event.newValue) return;
    try {
      handle(JSON.parse(event.newValue) as SyncMessage);
    } catch {
      // Ignore malformed browser state; no research or credential data is stored here.
    }
  };
  const subscriber =
    typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(CHANNEL_NAME);
  const handleBroadcast = (event: MessageEvent<SyncMessage>) => handle(event.data);

  window.addEventListener(EVENT_NAME, handleLocal);
  window.addEventListener("storage", handleStorage);
  subscriber?.addEventListener("message", handleBroadcast);
  return () => {
    window.removeEventListener(EVENT_NAME, handleLocal);
    window.removeEventListener("storage", handleStorage);
    subscriber?.removeEventListener("message", handleBroadcast);
    subscriber?.close();
  };
}
