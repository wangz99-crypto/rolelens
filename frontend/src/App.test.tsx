import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { roleBriefRequestFromTrusted } from "./pages/DecisionRoomPage";
import {
  demoDecisionFixture,
  evidenceDetailFixture,
  heroBriefSetFixture,
  heroRevisionFixture,
  sevenPercentBriefSetFixture,
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

function evidenceCalls() {
  return vi.mocked(fetch).mock.calls.filter(([input]) =>
    String(input).endsWith("/api/demo/decision/evidence"),
  );
}

function roleBriefCalls() {
  return vi.mocked(fetch).mock.calls.filter(([input]) =>
    String(input).endsWith("/api/demo/decision/role-brief"),
  );
}

describe("RoleLens Slice 3 flow", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        return Promise.resolve(
          jsonResponse(
            url.endsWith("/evidence")
              ? evidenceDetailFixture
              : url.includes("recalculate")
              ? heroRevisionFixture
              : demoDecisionFixture,
          ),
        );
      }),
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

  it("loads Evidence lazily once, shows seven items, and expands bounded detail", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    expect(evidenceCalls()).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "View Evidence" }));
    const drawer = await screen.findByRole("dialog", { name: "Evidence Foundation" });
    expect(evidenceCalls()).toHaveLength(1);
    for (const item of evidenceDetailFixture) {
      expect(within(drawer).getByText(item.label)).toBeInTheDocument();
    }
    expect(within(drawer).queryByText(evidenceDetailFixture[0].evidence_id)).not.toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: /Overall recorded churn/i }));
    expect(within(drawer).getByText(evidenceDetailFixture[0].evidence_id)).toBeInTheDocument();
    expect(within(drawer).getByText("Deterministic")).toBeInTheDocument();
    expect(within(drawer).getAllByText("Observed evidence").length).toBeGreaterThanOrEqual(1);
    expect(within(drawer).getByText(evidenceDetailFixture[0].limitations[0], { exact: false })).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.click(screen.getByRole("button", { name: "View Evidence" }));
    await screen.findByRole("dialog", { name: "Evidence Foundation" });
    expect(evidenceCalls()).toHaveLength(1);
  });

  it("keeps the Decision Room intact when Evidence detail loading fails", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) =>
      Promise.resolve(
        String(input).endsWith("/evidence")
          ? jsonResponse({}, false)
          : jsonResponse(demoDecisionFixture),
      ),
    );
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    await user.click(screen.getByRole("button", { name: "View Evidence" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Evidence details could not be loaded safely.",
    );
    expect(screen.getByRole("heading", { name: "Customer Retention Pilot" })).toBeInTheDocument();
    expect(screen.getAllByText("+5,000 USD")).toHaveLength(2);
  });

  it("shows trusted Hero depth for Sales, Analyst, and Data Engineer", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await screen.findByText("REV-002 · HUMAN REVISION");

    await user.click(screen.getByTestId("role-node-sales_marketing"));
    let drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    expect(within(drawer).getAllByText(/Blocked by scenario/i).length).toBeGreaterThanOrEqual(1);
    expect(within(drawer).getByText("BLOCKED")).toBeInTheDocument();
    expect(within(drawer).getByText("-7,500 USD")).toBeInTheDocument();
    expect(within(drawer).getByText("8% → 3%", { exact: false })).toBeInTheDocument();
    expect(within(drawer).getByText("Overall recorded churn")).toBeInTheDocument();
    expect(within(drawer).queryByText("TotalCharges parseability")).not.toBeInTheDocument();
    expect(within(drawer).getByText("IBM Granite Brief")).toBeInTheDocument();
    expect(within(drawer).getByText("NOT GENERATED")).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.click(screen.getByTestId("role-node-data_analyst"));
    drawer = await screen.findByRole("dialog", { name: "Data Analyst" });
    expect(within(drawer).getAllByText("Evidence basis remains valid").length).toBeGreaterThanOrEqual(1);
    expect(within(drawer).getByText("UNCHANGED")).toBeInTheDocument();
    expect(within(drawer).getByText("Scenario revisions do not rewrite observed Evidence.")).toBeInTheDocument();
    expect(within(drawer).queryByText("Current Scenario")).not.toBeInTheDocument();
    expect(within(drawer).getByText("NOT GENERATED")).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.click(screen.getByTestId("role-node-data_engineer"));
    drawer = await screen.findByRole("dialog", { name: "Data Engineer" });
    expect(within(drawer).getAllByText("Data foundation remains valid").length).toBeGreaterThanOrEqual(1);
    expect(within(drawer).getByText("Data Health unchanged")).toBeInTheDocument();
    expect(within(drawer).getByText("Source provenance unchanged")).toBeInTheDocument();
    expect(within(drawer).getByText("TotalCharges parseability")).toBeInTheDocument();
    expect(within(drawer).queryByText("Overall recorded churn")).not.toBeInTheDocument();
    expect(within(drawer).getByText("NOT GENERATED")).toBeInTheDocument();
    expect(evidenceCalls()).toHaveLength(1);
  });

  it("shows an honest baseline-only Revision History before recalculation", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    await user.click(screen.getByRole("button", { name: "Open Revision History" }));

    const drawer = await screen.findByRole("dialog", { name: "Revision History" });
    const baseline = within(drawer).getByTestId("revision-rev-001");
    expect(within(baseline).getByText("CURRENT")).toBeInTheDocument();
    expect(within(baseline).getByText("8%")).toBeInTheDocument();
    expect(within(baseline).getByText("+5,000 USD")).toBeInTheDocument();
    expect(within(drawer).getByText("No human revision has been calculated in this session.")).toBeInTheDocument();
    expect(within(drawer).queryByTestId("revision-rev-002")).not.toBeInTheDocument();
  });

  it("shows the accepted 8% to 3% revision and unchanged foundations", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await screen.findByText("REV-002 · HUMAN REVISION");
    await user.click(screen.getByRole("button", { name: "Open Revision History" }));

    const drawer = await screen.findByRole("dialog", { name: "Revision History" });
    const revision = within(drawer).getByTestId("revision-rev-002");
    expect(within(revision).getByText("8% → 3%")).toBeInTheDocument();
    expect(within(revision).getByText("+5,000 USD → -7,500 USD")).toBeInTheDocument();
    expect(within(revision).getByText("Clears → Does not clear")).toBeInTheDocument();
    expect(within(revision).getByText("Executive").nextSibling).toHaveTextContent("CHANGED");
    expect(within(revision).getByText("Sales / Marketing").nextSibling).toHaveTextContent("BLOCKED");
    expect(within(revision).getByText("Project Manager").nextSibling).toHaveTextContent("CHANGED");
    expect(within(revision).getByText("7 Evidence Objects").nextSibling).toHaveTextContent("UNCHANGED");
  });

  it("replaces REV-002 with the latest accepted 8% to 7% recalculation", async () => {
    let revisionRequest = 0;
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/evidence")) return Promise.resolve(jsonResponse(evidenceDetailFixture));
      if (options?.method === "POST") {
        revisionRequest += 1;
        return Promise.resolve(jsonResponse(revisionRequest === 1 ? heroRevisionFixture : sevenPercentRevisionFixture));
      }
      return Promise.resolve(jsonResponse(demoDecisionFixture));
    });
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
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await screen.findByText("Scenario changed; decision posture remains the same");
    await user.click(screen.getByRole("button", { name: "Open Revision History" }));

    const drawer = await screen.findByRole("dialog", { name: "Revision History" });
    expect(within(drawer).getAllByTestId("revision-rev-002")).toHaveLength(1);
    expect(within(drawer).getByText("8% → 7%")).toBeInTheDocument();
    expect(within(drawer).getByText("+5,000 USD → +2,500 USD")).toBeInTheDocument();
    expect(within(drawer).getByText("Still clears")).toBeInTheDocument();
    expect(within(drawer).queryByText("REV-003")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("Decision posture changed")).not.toBeInTheDocument();
  });

  it("keeps Role Lens and Revision History on trusted 3% while a 7% draft is unsaved", async () => {
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

    await user.click(screen.getByTestId("role-node-sales_marketing"));
    let drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    expect(within(drawer).getByText("An unsaved assumption edit is not reflected in this view.")).toBeInTheDocument();
    expect(within(drawer).getByText("8% → 3%", { exact: false })).toBeInTheDocument();
    expect(within(drawer).queryByText("8% → 7%", { exact: false })).not.toBeInTheDocument();
    expect(within(drawer).getByText("-7,500 USD")).toBeInTheDocument();

    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.click(screen.getByRole("button", { name: "Open Revision History" }));
    drawer = await screen.findByRole("dialog", { name: "Revision History" });
    expect(within(drawer).getByText("8% → 3%")).toBeInTheDocument();
    expect(within(drawer).queryByText("8% → 7%")).not.toBeInTheDocument();
    expect(within(drawer).getByText("+5,000 USD → -7,500 USD")).toBeInTheDocument();
  });

  it("shows only the safe product error when initial loading fails", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("secret traceback"));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /open demo workspace/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("RoleLens could not load the demo decision safely."));
    expect(screen.queryByText(/secret traceback/i)).not.toBeInTheDocument();
  });

  it("starts NOT GENERATED and never calls Granite automatically", async () => {
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    expect(screen.getByText("AI Brief not generated")).toBeInTheDocument();
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    const drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    expect(within(drawer).getByText("NOT GENERATED")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Generate Role Brief" })).toBeEnabled();
    expect(roleBriefCalls()).toHaveLength(0);
  });

  it("uses one Granite POST to make all five returned role briefs CURRENT", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) return Promise.resolve(jsonResponse(evidenceDetailFixture));
      if (url.endsWith("/role-brief")) return Promise.resolve(jsonResponse(heroBriefSetFixture));
      if (url.endsWith("/recalculate")) return Promise.resolve(jsonResponse(heroRevisionFixture));
      return Promise.resolve(jsonResponse(demoDecisionFixture));
    });
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await screen.findByText("AI Brief not generated");
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    let drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    expect(within(drawer).getAllByText("Blocked by scenario")).toHaveLength(2);
    expect(within(drawer).getByText("BLOCKED")).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Generate Role Brief" }));
    expect(await within(drawer).findByText("CURRENT")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Generate Role Brief" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Refresh Role Brief" })).not.toBeInTheDocument();
    expect(within(drawer).getByText("Sales 3% interpretation explains the trusted posture.")).toBeInTheDocument();
    for (const heading of ["Why it matters", "What still holds", "What to verify next", "Next handoff", "Grounding"]) {
      expect(within(drawer).getByText(heading)).toBeInTheDocument();
    }
    expect(roleBriefCalls()).toHaveLength(1);
    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.click(screen.getByTestId("role-node-data_analyst"));
    drawer = await screen.findByRole("dialog", { name: "Data Analyst" });
    expect(within(drawer).getByText("CURRENT")).toBeInTheDocument();
    expect(within(drawer).getByText("Data Analyst 3% interpretation explains the trusted posture.")).toBeInTheDocument();
    expect(roleBriefCalls()).toHaveLength(1);
  });

  it("keeps a trusted 3% brief CURRENT during an unsaved 7% draft", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) return Promise.resolve(jsonResponse(evidenceDetailFixture));
      if (url.endsWith("/role-brief")) return Promise.resolve(jsonResponse(heroBriefSetFixture));
      if (url.endsWith("/recalculate")) return Promise.resolve(jsonResponse(heroRevisionFixture));
      return Promise.resolve(jsonResponse(demoDecisionFixture));
    });
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    let drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    await user.click(within(drawer).getByRole("button", { name: "Generate Role Brief" }));
    await within(drawer).findByText("CURRENT");
    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.clear(lift);
    await user.type(lift, "7");
    expect(screen.getByText("AI Brief current")).toBeInTheDocument();
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    expect(within(drawer).getByText("CURRENT")).toBeInTheDocument();
    expect(within(drawer).getByText("-7,500 USD")).toBeInTheDocument();
    expect(within(drawer).getByText("Recalculate or revert the unsaved assumption edit before generating a new brief.")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Generate Role Brief" })).not.toBeInTheDocument();
    expect(roleBriefCalls()).toHaveLength(1);
  });

  it("derives STALE after accepting 7% and refreshes all five briefs together", async () => {
    let revisionCount = 0;
    let briefCount = 0;
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) return Promise.resolve(jsonResponse(evidenceDetailFixture));
      if (url.endsWith("/role-brief")) {
        briefCount += 1;
        return Promise.resolve(jsonResponse(briefCount === 1 ? heroBriefSetFixture : sevenPercentBriefSetFixture));
      }
      if (url.endsWith("/recalculate")) {
        revisionCount += 1;
        return Promise.resolve(jsonResponse(revisionCount === 1 ? heroRevisionFixture : sevenPercentRevisionFixture));
      }
      return Promise.resolve(jsonResponse(demoDecisionFixture));
    });
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    let drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    await user.click(within(drawer).getByRole("button", { name: "Generate Role Brief" }));
    await within(drawer).findByText("CURRENT");
    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.clear(lift);
    await user.type(lift, "7");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    expect(await screen.findByText("AI Brief stale")).toBeInTheDocument();
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    expect(within(drawer).getByText("STALE")).toBeInTheDocument();
    expect(within(drawer).getByText("This brief was generated for the previous accepted decision state.")).toBeInTheDocument();
    expect(within(drawer).getByText("Sales 3% interpretation explains the trusted posture.")).toBeInTheDocument();
    expect(within(drawer).getByText("+2,500 USD")).toBeInTheDocument();
    expect(within(drawer).getAllByText("Eligible for pilot review")).toHaveLength(2);
    await user.click(within(drawer).getByRole("button", { name: "Refresh Role Brief" }));
    expect(await within(drawer).findByText("CURRENT")).toBeInTheDocument();
    expect(within(drawer).getByText("Sales 7% interpretation explains the trusted posture.")).toBeInTheDocument();
    expect(roleBriefCalls()).toHaveLength(2);
  });

  it("preserves the stale brief when refresh fails", async () => {
    let revisionCount = 0;
    let briefCount = 0;
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) return Promise.resolve(jsonResponse(evidenceDetailFixture));
      if (url.endsWith("/role-brief")) {
        briefCount += 1;
        return Promise.resolve(briefCount === 1 ? jsonResponse(heroBriefSetFixture) : jsonResponse({}, false));
      }
      if (url.endsWith("/recalculate")) {
        revisionCount += 1;
        return Promise.resolve(jsonResponse(revisionCount === 1 ? heroRevisionFixture : sevenPercentRevisionFixture));
      }
      return Promise.resolve(jsonResponse(demoDecisionFixture));
    });
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    let drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    await user.click(within(drawer).getByRole("button", { name: "Generate Role Brief" }));
    await within(drawer).findByText("CURRENT");
    await user.click(within(drawer).getByRole("button", { name: "Close drawer" }));
    await user.clear(lift);
    await user.type(lift, "7");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    await user.click(within(drawer).getByRole("button", { name: "Refresh Role Brief" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("IBM Granite Role Brief could not be generated safely.");
    expect(within(drawer).getByText("STALE")).toBeInTheDocument();
    expect(within(drawer).getByText("Sales 3% interpretation explains the trusted posture.")).toBeInTheDocument();
  });

  it("keeps NOT GENERATED and deterministic state when initial generation fails", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) return Promise.resolve(jsonResponse(evidenceDetailFixture));
      if (url.endsWith("/role-brief")) return Promise.resolve(jsonResponse({}, false));
      return Promise.resolve(jsonResponse(demoDecisionFixture));
    });
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    const drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    await user.click(within(drawer).getByRole("button", { name: "Generate Role Brief" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("IBM Granite Role Brief could not be generated safely.");
    expect(within(drawer).getByText("NOT GENERATED")).toBeInTheDocument();
    expect(within(drawer).queryByText("Why it matters")).not.toBeInTheDocument();
    expect(within(drawer).getAllByText("Eligible for pilot review")).toHaveLength(2);
  });

  it("constructs role-brief requests only from accepted trusted assumptions", () => {
    const request = roleBriefRequestFromTrusted(heroRevisionFixture.assumptions);
    expect(request.expected_incremental_lift).toBe("0.03");
    expect(JSON.stringify(request)).not.toContain("0.07");
  });

  it("renders no prohibited AI overclaim in the primary successful flow", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) return Promise.resolve(jsonResponse(evidenceDetailFixture));
      if (url.endsWith("/role-brief")) return Promise.resolve(jsonResponse(heroBriefSetFixture));
      if (url.endsWith("/recalculate")) return Promise.resolve(jsonResponse(heroRevisionFixture));
      return Promise.resolve(jsonResponse(demoDecisionFixture));
    });
    const user = userEvent.setup();
    render(<App />);
    await enterDecisionRoom(user);
    const lift = screen.getByLabelText("Expected lift (%)");
    await user.clear(lift);
    await user.type(lift, "3");
    await user.click(screen.getByRole("button", { name: "Recalculate Impact" }));
    await user.click(screen.getByTestId("role-node-sales_marketing"));
    const drawer = await screen.findByRole("dialog", { name: "Sales / Marketing" });
    await user.click(within(drawer).getByRole("button", { name: "Generate Role Brief" }));
    await within(drawer).findByText("CURRENT");
    const rendered = document.body.textContent?.toLowerCase() ?? "";
    for (const forbidden of [
      "ai approved",
      "granite approved",
      "approval granted",
      "ai decided",
      "customer will churn",
      "high-risk customer",
      "target customers",
      "contact customers",
      "predicted roi",
    ]) {
      expect(rendered).not.toContain(forbidden);
    }
  });
});
