import React from "react";
import { clsx } from "clsx";

export interface Column<T> {
  header: string;
  render: (row: T, index: number) => React.ReactNode;
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T, index: number) => string | number;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  onRowClick,
  emptyMessage = "Aucune donnée disponible",
  className,
}: DataTableProps<T>) {
  return (
    <div className={clsx("w-full overflow-x-auto rounded-xl border border-border-subtle bg-surface-lowest", className)}>
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-border-subtle bg-surface-low/50">
            {columns.map((col, idx) => (
              <th
                key={idx}
                className={clsx(
                  "px-6 py-4 text-label-caps text-on-surface-variant font-bold select-none whitespace-nowrap",
                  col.className,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {data.length > 0 ? (
            data.map((row, rowIdx) => (
              <tr
                key={keyExtractor(row, rowIdx)}
                onClick={() => onRowClick?.(row)}
                className={clsx(
                  "transition-colors duration-150 text-body-md text-on-surface",
                  onRowClick && "cursor-pointer hover:bg-surface-safe",
                  !onRowClick && "hover:bg-surface-low/30",
                )}
              >
                {columns.map((col, colIdx) => (
                  <td
                    key={colIdx}
                    className={clsx(
                      "px-6 py-4 whitespace-nowrap align-middle",
                      col.className,
                    )}
                  >
                    {col.render(row, rowIdx)}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td
                colSpan={columns.length}
                className="px-6 py-10 text-center text-body-md text-on-surface-variant/60 bg-surface-lowest"
              >
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
