import { tool } from '@openai/agents/realtime';

// Minimal sample data placeholders
const exampleAccountInfo = { account_id: 'ACC-123', balance_usd: 42.5 };
const examplePolicyDocs = [
  {
    id: 'ID-001',
    name: 'Sample Policy',
    topic: 'general',
    content: 'Sample content.',
  },
];
const exampleStoreLocations = [
  { id: 'STORE-1', zip: '98101', name: 'Downtown Store' },
];

export const supervisorAgentInstructions = `You are a supervisor providing guidance.`;

export const supervisorAgentTools = [
  {
    type: 'function',
    name: 'lookupPolicyDocument',
    description: 'Lookup internal documents and policies by topic.',
    parameters: {
      type: 'object',
      properties: { topic: { type: 'string' } },
      required: ['topic'],
      additionalProperties: false,
    },
  },
  {
    type: 'function',
    name: 'getUserAccountInfo',
    description: 'Get user account information.',
    parameters: {
      type: 'object',
      properties: { phone_number: { type: 'string' } },
      required: ['phone_number'],
      additionalProperties: false,
    },
  },
  {
    type: 'function',
    name: 'findNearestStore',
    description: 'Find nearest store by zip.',
    parameters: {
      type: 'object',
      properties: { zip_code: { type: 'string' } },
      required: ['zip_code'],
      additionalProperties: false,
    },
  },
];

// Removed server-side /api/responses usage

function getToolResponse(name: string) {
  switch (name) {
    case 'getUserAccountInfo':
      return exampleAccountInfo;
    case 'lookupPolicyDocument':
      return examplePolicyDocs;
    case 'findNearestStore':
      return exampleStoreLocations;
    default:
      return { result: true };
  }
}

// Removed tool call loop using Responses API

export const getNextResponseFromSupervisor = tool({
  name: 'getNextResponseFromSupervisor',
  description:
    'Determines the next response using a higher-level supervisor agent.',
  parameters: {
    type: 'object',
    properties: {
      relevantContextFromLastUserMessage: {
        type: 'string',
        description: 'Key info from the most recent user message.',
      },
    },
    required: ['relevantContextFromLastUserMessage'],
    additionalProperties: false,
  },
  execute: async (input, details) => {
    const { relevantContextFromLastUserMessage } = input as {
      relevantContextFromLastUserMessage: string;
    };
    const addBreadcrumb = (details?.context as any)?.addTranscriptBreadcrumb as
      | ((title: string, data?: any) => void)
      | undefined;
    // Defer to backend orchestration; as a placeholder, echo the hint
    return {
      nextResponse: `Supervisor hint: ${relevantContextFromLastUserMessage}`,
    };
  },
});
