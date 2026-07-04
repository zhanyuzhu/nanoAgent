import { useRef, useState } from "react";

interface Props {
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export default function Composer({ streaming, onSend, onStop }: Props) {
  const [text, setText] = useState("");
  const areaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;
    onSend(trimmed);
    setText("");
    if (areaRef.current) areaRef.current.style.height = "auto";
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={areaRef}
          value={text}
          rows={1}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          onChange={(e) => {
            setText(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {streaming ? (
          <button className="send-btn stop" title="停止生成" onClick={onStop}>
            ◼
          </button>
        ) : (
          <button className="send-btn" title="发送" disabled={!text.trim()} onClick={submit}>
            ↑
          </button>
        )}
      </div>
      <div className="composer-hint">nanoAgent 可能会犯错，重要信息请自行核实</div>
    </div>
  );
}
