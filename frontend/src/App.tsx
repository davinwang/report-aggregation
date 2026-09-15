// App root: wires providers — TanStack Query, Ant Design ConfigProvider (themed by
// uiStore, zh_CN locale), dayjs locale, and BrowserRouter around the route tree.
import { useEffect, useMemo } from "react";
import { ConfigProvider, App as AntdApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import "dayjs/locale/zh-cn";
import AppRoutes from "@/router";
import { useUIStore } from "@/stores/uiStore";
import { lightTheme, darkTheme } from "@/styles/theme";
import { AntdMessageBridge } from "@/utils/message";

export default function App() {
  const mode = useUIStore((s) => s.mode);
  const themeConfig = mode === "dark" ? darkTheme : lightTheme;

  // Expose mode to CSS so global utility styles (scrollbars, ticker, muted text)
  // can follow the active terminal theme.
  useEffect(() => {
    document.body.dataset.theme = mode;
  }, [mode]);

  // Single QueryClient for the app lifetime; staleTime tuned to daily-data freshness.
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            gcTime: 5 * 60_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
    [],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={zhCN} theme={themeConfig}>
        <AntdApp>
          <AntdMessageBridge />
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </AntdApp>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
