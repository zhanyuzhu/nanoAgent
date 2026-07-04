import type { Block } from "../types";

const TOOL_LABELS: Record<string, string> = {
  calculator: "计算器",
  search: "搜索",
  read_docs: "查阅文档",
  save_memory: "记入长期记忆",
};

interface Props {
  block: Block;
  onToggle: (id: string) => void;
}

export default function ToolBlock({ block, onToggle }: Props) {
  const name = block.toolName ?? "工具";
  const label = TOOL_LABELS[name] ?? name;
  const argsText = block.done
    ? JSON.stringify(block.args ?? {}, null, 2)
    : block.text || "…";

  return (
    <div className={`tool-block ${block.status === "error" ? "failed" : ""}`}>
      <button className="tool-header" onClick={() => onToggle(block.id)}>
        <span className={`chevron ${block.open ? "down" : ""}`}>▸</span>
        <span className="tool-icon">⚙</span>
        <span className="tool-name">
          {label}
          <span className="tool-raw-name">{name}</span>
        </span>
        <span className="tool-status">
          {!block.done && <span className="spinner" />}
          {block.done && block.status === "ok" && <span className="status-ok">✓</span>}
          {block.done && block.status === "error" && <span className="status-err">✗</span>}
        </span>
      </button>
      {block.open && (
        <div className="tool-body">
          <div className="tool-section-label">参数</div>
          <pre className="tool-pre">{argsText}</pre>
          {block.result !== undefined && (
            <>
              <div className="tool-section-label">结果</div>
              <pre className="tool-pre tool-result">{block.result}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}
