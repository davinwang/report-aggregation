// Theme-aware antd message bridge. The axios interceptor (client.ts) runs outside
// React, so it can't call App.useApp() directly. App renders <AntdMessageBridge/>
// inside <App>, which registers the context-aware instance here; callers use `msg`.
// Falls back to the static antd message until the bridge mounts.
import { useEffect } from "react";
import { App, message as staticMessage } from "antd";

type MessageApi = ReturnType<typeof App.useApp>["message"];

let instance: MessageApi | null = null;

export function setMessageApi(api: MessageApi | null): void {
  instance = api;
}

// Stable facade delegating to the context instance when available.
export const msg = {
  error: (content: string) => (instance ?? staticMessage).error(content),
  success: (content: string) => (instance ?? staticMessage).success(content),
  info: (content: string) => (instance ?? staticMessage).info(content),
  warning: (content: string) => (instance ?? staticMessage).warning(content),
  loading: (content: string) => (instance ?? staticMessage).loading(content),
};

// Render inside <App> to wire the context-aware message instance.
export function AntdMessageBridge(): null {
  const { message } = App.useApp();
  useEffect(() => {
    setMessageApi(message);
    return () => setMessageApi(null);
  }, [message]);
  return null;
}
