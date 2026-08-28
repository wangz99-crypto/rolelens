import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  demoDecisionFixture,
  heroRevisionFixture,
  sevenPercentRevisionFixture,
} from "./test/fixture";

function jsonResponse(payload: unknown, ok = true) {
  return { ok, json: async () => payload } as Response;
}

async function enterDecisionRoom(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
  await user.click(await screen.findByRole("button", { name: /open decision/i }));
}

function postCalls() {
  return vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === "POST");
}

describe("RoleLens Slice 2 flow", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve(
          jsonResponse(
            url.includes("recalculate")
              ? heroRevisionFixture
              : demoDecisionFixture,
          ),
        ),
      ),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("preserves the accepted Landing and fetches only after its CTA", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByRole("heading", { name: "Know what must change when the decision changes." })).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await screen.findByRole("heading", { name: "Decisions" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps exactly one real Decision on Decision Home", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await screen.findByRole("heading", { name: "Decisions" });
    expect(screen.getAllByTestId("decision-card")).toHaveLength(1);
    expect(screen.queryByText(/new decision/i)).not.toBeInTheDocument();
  });

  it("starts with four editable baseline assumptions and no unsaved revision", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    expect(screen.getByLabelText("Pilot population")).toHaveValue(500);
    expect(screen.getByLabelText("Expected lift (%)")).toHaveValue("8.0");
    expect(screen.getByLabelText("Cost / intervention")).toHaveValue(30);
    expect(screen.getByLabelText("Retained value")).toHaveValue(500);
    expect(screen.queryByText("UNSAVED REVISION")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recalculate Impact" })).toBeDisabled();
    expect(screen.getAllByText("+5,000 USD")).toHaveLength(2);
    expect(within(screen.getByTestId("role-node-sales_marketing")).getByText("Eligible for pilot review")).toBeInTheDocument();
  });

  it("marks an 8% to 3% draft unsaved without changing the trusted map", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    expect(screen.getByText("UNSAVED REVISION")).toBeInTheDocument();
    expect(screen.getByText("Impact Map still reflects the last calculated decision.")).toBeInTheDocument();
    expect(postCalls()).toHaveLength(0);
    expect(screen.getAllByText("+5,000 USD")).toHaveLength(2);
    expect(within(screen.getByTestId("role-node-sales_marketing")).getByText("Eligible for pilot review")).toBeInTheDocument();
  });

  it("propagates the Hero response in place through all five role states", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));

    expect(await screen.findByText("REV-002 · HUMAN REVISION")).toBeInTheDocument();
    expect(screen.getAllByText("-7,500 USD").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Does not clear modeled break-even").length).toBeGreaterThanOrEqual(1);
    expect(within(screen.getByTestId("role-node-executive")).getByText("CHANGED")).toBeInTheDocument();
    expect(within(screen.getByTestId("role-node-sales_marketing")).getByText("BLOCKED")).toBeInTheDocument();
    expect(within(screen.getByTestId("role-node-project_manager")).getByText("CHANGED")).toBeInTheDocument();
    expect(within(screen.getByTestId("role-node-data_analyst")).getByText("UNCHANGED")).toBeInTheDocument();
    expect(within(screen.getByTestId("role-node-data_engineer")).getByText("UNCHANGED")).toBeInTheDocument();
    expect(screen.getByText("The decision changed. The observed evidence did not.")).toBeInTheDocument();
    expect(screen.getByText("AI Brief not generated")).toBeInTheDocument();
    expect(screen.queryByText("AI Brief stale")).not.toBeInTheDocument();
    expect(postCalls()).toHaveLength(1);
    expect(JSON.parse(String(postCalls()[0][1]?.body))).toMatchObject({ expected_incremental_lift: "0.03" });
  });

  it("serializes a 33.3% edit as the exact decimal string 0.333", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "33.3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));

    await waitFor(() => expect(postCalls()).toHaveLength(1));
    const request = JSON.parse(String(postCalls()[0][1]?.body));
    expect(request.expected_incremental_lift).toBe("0.333");
    expect(String(postCalls()[0][1]?.body)).not.toContain("0.33299999999999996");
  });

  it("renders 8% to 7% as recomputed and never blocks Sales", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) =>
      Promise.resolve(jsonResponse(String(input).includes("recalculate") ? sevenPercentRevisionFixture : demoDecisionFixture)),
    );
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "7");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));

    expect(await screen.findByText("Scenario changed; decision posture remains the same")).toBeInTheDocument();
    expect((lift as HTMLInputElement).value).toBe("7.0");
    expect(document.body.textContent).not.toContain("7.000000000000001");
    expect(JSON.parse(String(postCalls()[0][1]?.body))).toMatchObject({ expected_incremental_lift: "0.07" });
    expect(screen.getAllByText("+2,500 USD").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Scenario clears")).toBeInTheDocument();
    expect(within(screen.getByTestId("role-node-executive")).getByText("RECOMPUTED")).toBeInTheDocument();
    expect(within(screen.getByTestId("role-node-sales_marketing")).getByText("RECOMPUTED")).toBeInTheDocument();
    expect(within(screen.getByTestId("role-node-project_manager")).getByText("RECOMPUTED")).toBeInTheDocument();
    expect(screen.queryByText("Blocked by scenario")).not.toBeInTheDocument();
  });

  it("preserves the draft and last trusted map when recalculation fails", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) =>
      Promise.resolve(String(input).includes("recalculate") ? jsonResponse({}, false) : jsonResponse(demoDecisionFixture)),
    );
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Decision impact could not be recalculated safely.");
    expect(lift).toHaveValue("3");
    expect(screen.getByText("UNSAVED REVISION")).toBeInTheDocument();
    expect(screen.getAllByText("+5,000 USD")).toHaveLength(2);
    expect(within(screen.getByTestId("role-node-sales_marketing")).getByText("Eligible for pilot review")).toBeInTheDocument();
  });

  it("keeps the 3% trusted result while a new 7% draft remains unsaved", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await screen.findByText("REV-002 · HUMAN REVISION");
    await user.clear(lift);
    await user.type(lift, "7");

    expect(lift).toHaveValue("7");
    expect(screen.getByText("UNSAVED REVISION")).toBeInTheDocument();
    expect(screen.getAllByText("-7,500 USD").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("+2,500 USD")).not.toBeInTheDocument();
    expect(postCalls()).toHaveLength(1);
  });

  it("uses only bounded product copy in the revised room", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await screen.findByText("REV-002 · HUMAN REVISION");
    const rendered = document.body.textContent ?? "";
    for (const forbidden of [
      "AI decided",
      "AI approved",
      "approval granted",
      "ROI prediction",
      "prediction probability",
      "high-risk customers",
      "contact customers",
      "customer targeting",
      "Evidence supports the break-even calculation",
    ]) {
      expect(rendered).not.toContain(forbidden);
    }
  });

  it("renders NOT_EVALUABLE with neutral or warning visuals", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        ...demoDecisionFixture,
        scenario: {
          ...demoDecisionFixture.scenario,
          status: "NOT_EVALUABLE",
        },
      }),
    );
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);

    expect(screen.getByText("Scenario not evaluable")).toHaveClass(
      "text-slate-300",
    );
    expect(screen.getByText("Not evaluable")).toHaveClass("text-amber-200");
    expect(screen.getByText("NOT EVALUABLE")).toHaveClass("text-amber-200");
  });

  it("shows only the safe product error when initial loading fails", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("secret traceback"));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("RoleLens could not load the demo decision safely."));
    expect(screen.queryByText(/secret traceback/i)).not.toBeInTheDocument();
  });
});
