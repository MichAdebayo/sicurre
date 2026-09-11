// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent, act } from "@testing-library/react";
import { useState } from "react";
import { Dialog } from "../../../src/app/components/ui/dialog";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open
      </button>
      <Dialog
        isOpen={open}
        onClose={() => {
          onClose();
          setOpen(false);
        }}
        title="Titre"
        description="Description"
        footer={
          <>
            <button type="button">annuler</button>
            <button type="button">confirmer</button>
          </>
        }
      >
        <p>corps</p>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  afterEach(cleanup);

  it("is a labelled modal dialog with a named close control", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("open"));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Titre");
    expect(dialog).toHaveAccessibleDescription("Description");
    expect(screen.getByRole("button", { name: "common.close" })).toBeInTheDocument();
  });

  it("moves focus inside on open and returns it on close", async () => {
    render(<Harness />);
    const opener = screen.getByText("open");
    opener.focus();
    fireEvent.click(opener);
    await act(async () => {});
    const closeButton = screen.getByRole("button", { name: "common.close" });
    expect(document.activeElement).toBe(closeButton);
    fireEvent.keyDown(closeButton, { key: "Escape" });
    await act(async () => {});
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener);
  });

  it("closes on Escape and on the backdrop", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("keeps Tab inside the panel", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("open"));
    await act(async () => {});
    const closeButton = screen.getByRole("button", { name: "common.close" });
    const confirm = screen.getByText("confirmer");
    confirm.focus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(document.activeElement).toBe(closeButton);
    fireEvent.keyDown(closeButton, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirm);
  });
});
