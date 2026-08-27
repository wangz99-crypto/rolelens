import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { demoDecisionFixture } from "./test/fixture";

describe("RoleLens Slice 1 flow", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => demoDecisionFixture,
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("shows the landing headline and waits for the CTA before fetching", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("heading", { name: "Know what must change when the decision changes." })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await screen.findByRole("heading", { name: "Decisions" });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("/api/demo/decision", expect.any(Object));
  });

  it("renders exactly one real decision on Decision Home", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await screen.findByRole("heading", { name: "Decisions" });
    expect(screen.getAllByTestId("decision-card")).toHaveLength(1);
    expect(screen.getByText(demoDecisionFixture.decision.business_question)).toBeInTheDocument();
    expect(screen.queryByText(/new decision/i)).not.toBeInTheDocument();
  });

  it("renders the bounded Decision Room with no edit or later-slice actions", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await user.click(await screen.findByRole("button", { name: /open decision/i }));

    expect(await screen.findAllByText("+5,000 USD")).toHaveLength(2);
    expect(screen.getAllByTestId(/^role-node-/)).toHaveLength(5);
    expect(screen.getByText("500 customers")).toBeInTheDocument();
    expect(screen.getByText("8.0%")).toBeInTheDocument();
    expect(screen.getByText("30 USD")).toBeInTheDocument();
    expect(screen.getByText("500 USD")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("governed findings")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /recalculate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /granite/i })).not.toBeInTheDocument();
  });

  it("shows only the safe product error when loading fails", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("secret traceback"));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("RoleLens could not load the demo decision safely.");
    });
    expect(screen.queryByText(/secret traceback/i)).not.toBeInTheDocument();
  });
});
