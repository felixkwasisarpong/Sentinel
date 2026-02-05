type GraphQLError = { message: string };

type GraphQLResponse<T> = {
  data?: T;
  errors?: GraphQLError[];
};

const DEFAULT_URL =
  process.env.NEXT_PUBLIC_GATEWAY_GRAPHQL_URL || "http://localhost:8000/graphql";

export async function gql<T>(
  query: string,
  variables?: Record<string, unknown>,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(DEFAULT_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    body: JSON.stringify({ query, variables: variables ?? {} }),
    ...init,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `GraphQL request failed: ${res.status}`);
  }

  const payload = (await res.json()) as GraphQLResponse<T>;
  if (payload.errors && payload.errors.length > 0) {
    throw new Error(payload.errors[0].message || "GraphQL error");
  }

  if (!payload.data) {
    throw new Error("GraphQL error: empty response");
  }

  return payload.data;
}
