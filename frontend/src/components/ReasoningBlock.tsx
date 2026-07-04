import type { Block } from "../types";

interface Props {
  block: Block;
  onToggle: (id: string) => void;
}

export default function ReasoningBlock({ block, onToggle }: Props) {
  const thinking = !block.done;
  return (
    <div className={`reasoning-block ${block.open ? "open" : ""}`}>
      <button className="reasoning-header" onClick={() => onToggle(block.id)}>
        <span className={`chevron ${block.open ? "down" : ""}`}>▸</span>
        <span className={thinking ? "shimmer" : ""}>
          {thinking ? "思考中…" : "思考过程"}
        </span>
      </button>
      {block.open && <div className="reasoning-body">{block.text}</div>}
    </div>
  );
}
