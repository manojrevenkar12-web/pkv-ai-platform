import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import raw from "../../public/data/console.json";
import type { Console } from "../shared/types";
import { App, headline } from "./App";

const data = raw as unknown as Console;

function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
}

const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const h1 = () => screen.getByRole("heading", { level: 1 }).textContent;

afterEach(() => vi.unstubAllGlobals());

describe("console", () => {
  it("shows a skeleton while the report loads", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    mount();
    expect(screen.getByLabelText("Loading")).toBeTruthy();
  });

  it("explains a failed load and retries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("", { status: 500 })).mockImplementation(() => ok(data)));
    mount();
    await screen.findByRole("alert");
    fireEvent.click(screen.getByText("Retry"));
    await waitFor(() => expect(h1()).toBe(headline(data.dev)));
  });

  it("says what to do when the report has no use cases", async () => {
    vi.stubGlobal("fetch", () => ok({ ...data, dev: { ...data.dev, selection: {} } }));
    mount();
    expect(await screen.findByText(/has no use cases/)).toBeTruthy();
  });

  it("draws one bar per live day and marks the alarm days", async () => {
    vi.stubGlobal("fetch", () => ok(data));
    const { container } = mount();
    await screen.findByRole("heading", { level: 1 });
    expect(container.querySelectorAll("rect.bar").length).toBe(data.dev.routing.daily.length);
    expect(container.querySelectorAll("rect.bar.alarm").length).toBe(data.dev.routing.daily.filter((d) => d.alarm).length);
  });

  it("opens a use case to show every candidate model and the verdict", async () => {
    vi.stubGlobal("fetch", () => ok(data));
    mount();
    const button = await screen.findByRole("button", { name: data.names.usecases.routing });
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    for (const t of data.dev.selection.routing.trials) expect(screen.getAllByText(t.model).length).toBeGreaterThan(0);
  });

  it("shows the settled invoice and why it was cut", async () => {
    vi.stubGlobal("fetch", () => ok(data));
    mount();
    await screen.findByRole("heading", { level: 1 });
    for (const n of data.dev.invoices.platform.example!.notes) expect(screen.getByText(n)).toBeTruthy();
  });

  it("switches to the held-out world when there is one", async () => {
    vi.stubGlobal("fetch", () => ok(data));
    mount();
    await screen.findByRole("heading", { level: 1 });
    if (!data.heldout) {
      expect(screen.queryByText("Held-out world")).toBeNull();
      return;
    }
    fireEvent.click(screen.getByText("Held-out world"));
    await waitFor(() => expect(h1()).toBe(headline(data.heldout!)));
  });
});
