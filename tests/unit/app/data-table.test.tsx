// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DataTable, type Column } from "../../../src/app/components/ui/data-table";

interface Row {
  id: number;
  domain: string;
  grade: string;
}

const rows: Row[] = [
  { id: 1, domain: "sicurre.com", grade: "A" },
  { id: 2, domain: "exemple.fr", grade: "C" },
];

const columns: Column<Row>[] = [
  { header: "Domaine", render: (row) => row.domain },
  { header: "Note", render: (row) => <strong>{row.grade}</strong>, className: "text-right" },
  { header: "Rang", render: (_row, index) => `#${index + 1}` },
];

afterEach(cleanup);

describe("DataTable", () => {
  it("renders one column header per column and one row per data item", () => {
    render(<DataTable columns={columns} data={rows} keyExtractor={(row) => row.id} />);

    const headers = screen.getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toEqual(["Domaine", "Note", "Rang"]);
    expect(headers[1]).toHaveClass("text-right");

    const bodyRows = within(screen.getAllByRole("rowgroup")[1]).getAllByRole("row");
    expect(bodyRows).toHaveLength(2);
    expect(within(bodyRows[0]).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "sicurre.com",
      "A",
      "#1",
    ]);
    expect(within(bodyRows[1]).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "exemple.fr",
      "C",
      "#2",
    ]);
    expect(within(bodyRows[0]).getAllByRole("cell")[1]).toHaveClass("text-right");
  });

  it("calls onRowClick with the clicked row and marks rows as clickable", () => {
    const onRowClick = vi.fn();
    render(
      <DataTable columns={columns} data={rows} keyExtractor={(row) => row.id} onRowClick={onRowClick} />,
    );

    const row = screen.getByText("exemple.fr").closest("tr") as HTMLTableRowElement;
    expect(row).toHaveClass("cursor-pointer");
    fireEvent.click(row);
    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(rows[1]);
  });

  it("leaves rows inert when no click handler is given", () => {
    render(<DataTable columns={columns} data={rows} keyExtractor={(row) => row.id} />);
    const row = screen.getByText("sicurre.com").closest("tr") as HTMLTableRowElement;
    expect(row).not.toHaveClass("cursor-pointer");
    expect(() => fireEvent.click(row)).not.toThrow();
  });

  it("shows the default French empty message spanning every column when there is no data", () => {
    render(<DataTable columns={columns} data={[]} keyExtractor={(row) => row.id} />);
    const cell = screen.getByText("Aucune donnée disponible");
    expect(cell).toHaveAttribute("colspan", "3");
    expect(screen.getAllByRole("columnheader")).toHaveLength(3);
  });

  it("shows a custom empty message and applies the wrapper class name", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        data={[]}
        keyExtractor={(row) => row.id}
        emptyMessage="Aucun domaine surveillé"
        className="mt-8"
      />,
    );
    expect(screen.getByText("Aucun domaine surveillé")).toBeInTheDocument();
    expect(screen.queryByText("Aucune donnée disponible")).not.toBeInTheDocument();
    expect(container.firstElementChild).toHaveClass("mt-8");
  });

  it("uses keyExtractor with the row and its index", () => {
    const keyExtractor = vi.fn((row: Row, index: number) => `${row.id}-${index}`);
    render(<DataTable columns={columns} data={rows} keyExtractor={keyExtractor} />);
    expect(keyExtractor).toHaveBeenCalledWith(rows[0], 0);
    expect(keyExtractor).toHaveBeenCalledWith(rows[1], 1);
  });
});
