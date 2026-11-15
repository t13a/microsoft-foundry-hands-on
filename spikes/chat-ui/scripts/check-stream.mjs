// V-10 (part 1): drive the whole consultation through the official OpenAI JS SDK and print
// how each stream event is typed. Usage: node scripts/check-stream.mjs [baseURL]
import OpenAI from "openai";

const baseURL = process.argv[2] ?? "http://localhost:8088";
const client = new OpenAI({ baseURL, apiKey: "unused" });
const session = crypto.randomUUID().replaceAll("-", "");
let previous;

async function turn(label, input) {
  console.log(`\n== ${label}`);
  const stream = await client.responses.create({
    input,
    stream: true,
    store: true,
    previous_response_id: previous,
    agent_session_id: session, // Foundry-specific field; passed through as-is
  });
  let text = "";
  let response;
  for await (const event of stream) {
    if (event.type === "response.output_text.delta") text += event.delta;
    if (event.type === "response.output_item.done") {
      const item = event.item;
      const detail = item.type === "message" ? "" : ` name=${item.name ?? ""} call_id=${item.call_id ?? ""} id=${item.id}`;
      console.log(`  item ${item.type}${detail}`);
    }
    if (event.type === "response.completed" || event.type === "response.failed") response = event.response;
  }
  if (text) console.log(`  text: ${text}`);
  console.log(`  status: ${response.status}${response.error ? " " + JSON.stringify(response.error) : ""}`);
  previous = response.id;
  return response.output;
}

const pendingInput = (output) => {
  const answered = new Set(output.filter((i) => i.type === "function_call_output").map((i) => i.call_id));
  const call = output.find((i) => i.type === "function_call" && i.name === "request_info" && !answered.has(i.call_id));
  return call && { callId: call.call_id, request: JSON.parse(call.arguments).request };
};
const reply = (pending, value) => [{ type: "function_call_output", call_id: pending.callId, output: JSON.stringify(value) }];
const approve = (output, approved) => {
  const req = output.find((i) => i.type === "mcp_approval_request");
  return [{ type: "mcp_approval_response", approval_request_id: req.id, approve: approved }];
};

let out = await turn("start", "start");
let pending = pendingInput(out);
console.log("  pending:", pending.request.request_type, pending.request.metadata.form);

out = await turn("profile form", reply(pending, { gender: "無回答", age: "30代", ward: "中央区" }));
pending = pendingInput(out);
console.log("  pending:", pending.request.request_type);

out = await turn("message", reply(pending, { text: "子どもの予防接種について", currentUrl: "/" }));
console.log("  approval:", out.find((i) => i.type === "mcp_approval_request")?.name);

out = await turn("approve display", approve(out, true));
pending = pendingInput(out);
console.log("  pending:", pending?.request.request_type);

out = await turn("message (end)", reply(pending, { text: "相談を終わる", currentUrl: "/search?q=予防接種" }));
console.log("  approval:", out.find((i) => i.type === "mcp_approval_request")?.name);

out = await turn("approve end", approve(out, true));
pending = pendingInput(out);
console.log("  pending:", pending?.request.request_type, pending?.request.metadata.form);

out = await turn("feedback form", reply(pending, { rating: 5, comment: "わかりやすかった" }));
console.log("  pending after feedback:", pendingInput(out) ?? "none (completed)");
