// 长文本截断 + 悬浮 tooltip。
// 用法：<Truncate text="很长的文本..." maxLines={1} />
// 鼠标悬停时通过 title 显示完整文本。

import { ReactNode, type CSSProperties } from "react";

interface TruncateProps {
  text: string | null | undefined;
  maxLines?: number;
  className?: string;
  /** 自定义 tooltip 文本，默认等于 text */
  title?: string;
  children?: ReactNode;
}

export default function Truncate({
  text,
  maxLines = 1,
  className = "",
  title,
  children,
}: TruncateProps) {
  const display = text ?? "";
  const lineClamp =
    maxLines > 1
      ? ({
          display: "-webkit-box",
          WebkitLineClamp: maxLines,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        } as CSSProperties)
      : ({
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        } as CSSProperties);

  return (
    <span
      className={`block ${className}`}
      style={lineClamp}
      title={title ?? (display || undefined)}
    >
      {children ?? display}
    </span>
  );
}
