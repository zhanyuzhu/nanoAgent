import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";

// 不用 StrictMode：dev 下的 effect 双跑会中止流式 SSE fetch
createRoot(document.getElementById("root")!).render(<App />);
