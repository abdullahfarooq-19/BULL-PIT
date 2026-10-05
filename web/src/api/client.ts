import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

/** The only way to the API: same-origin `/api/*`, rewritten to the FastAPI process. */
export const api = createClient<paths>({ baseUrl: "/api" });

export type Schemas = components["schemas"];
export type Report = Schemas["Report"];
export type Order = NonNullable<Report["order"]>;
export type RequestDetail = Schemas["RequestDetail"];
export type RequestSummary = Schemas["RequestSummary"];
export type TradeOut = Schemas["TradeOut"];
export type OrderPreview = Schemas["OrderPreview"];
export type OrderPreviewBody = Schemas["OrderPreviewBody"];

/** A refusal or failure, carrying the API's own message and its stable `code`. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly details: Partial<Schemas["ApprovalProblem"]> = {},
  ) {
    super(message);
  }
}

type Outcome<T> = { data?: T; error?: unknown; response: Response };

/** The data of a response, or an `ApiError` with the API's message.
 *  A stopped API shows up as a proxy error, which gets a message that says what to do. */
export async function unwrap<T>(call: Promise<Outcome<T>>): Promise<T> {
  let outcome: Outcome<T>;
  try {
    outcome = await call;
  } catch {
    throw new ApiError("unreachable", UNREACHABLE);
  }
  if (outcome.error !== undefined || outcome.data === undefined) {
    const body = outcome.error as Partial<Schemas["ApprovalProblem"]> | undefined;
    if (body && typeof body === "object" && body.code && body.message) {
      throw new ApiError(body.code, body.message, body);
    }
    throw new ApiError("unreachable", UNREACHABLE);
  }
  return outcome.data;
}

const UNREACHABLE = "The API isn't reachable. Start it with `bullpit serve`.";

/** Starts a live request and returns its ID (M8-FR-18). A duplicate or a bad ticker
 *  is an `ApiError` whose message can be shown as it is. */
export async function startRequest(ticker: string): Promise<string> {
  const started = await unwrap(api.POST("/requests", { body: { ticker } }));
  return started.request_id;
}

const TICKER = /^[A-Z][A-Z.]{0,9}$/;

/** The same rule the API applies to a ticker, after trimming and upper-casing. */
export function isTicker(value: string): boolean {
  return TICKER.test(value);
}
