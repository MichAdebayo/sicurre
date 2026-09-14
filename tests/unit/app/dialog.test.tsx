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

  it("dims the page without blurring it and keeps the panel still", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("open"));
    const backdrop = document.querySelector<HTMLElement>('div[aria-hidden="true"].absolute.inset-0');
    expect(backdrop).not.toBeNull();
    // Chromium draws a backdrop blur only once its fade ends, so it flickered.
    expect(backdrop!.className).not.toMatch(/backdrop-blur/);
    // A theme token flips to near-white in dark mode and washed the page out.
    expect(backdrop!.className).toMatch(/\bbg-black\/60\b/);
    expect(backdrop!.className).not.toMatch(/on-background/);
    // No fade either: the dim is there from the first frame.
    expect(backdrop).not.toHaveAttribute("style");
    // No fade or scale on the panel: an embedded frame showed through ahead of it.
    expect(screen.getByRole("dialog")).not.toHaveAttribute("style");
  });

  it("closes at once, without an exit animation holding it on screen", () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("open"));
    fireEvent.click(screen.getByRole("button", { name: "common.close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.querySelector('div[aria-hidden="true"].absolute.inset-0')).toBeNull();
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
