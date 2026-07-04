import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Block } from "../types";

export default function TextBlock({ block }: { block: Block }) {
  return (
    <div className="text-block markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
      {!block.done && <span className="cursor">▍</span>}
    </div>
  );
}
