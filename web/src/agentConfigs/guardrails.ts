import { GuardrailOutputZod, GuardrailOutput } from '@/types';

export async function runGuardrailClassifier(
  message: string,
  companyName: string = 'newTelco'
): Promise<GuardrailOutput> {
  const messages = [
    {
      role: 'user',
      content: `You are an expert at classifying text according to moderation policies. Consider the provided message, analyze potential classes from output_classes, and output the best classification. Output json, following the provided schema. Keep your analysis and reasoning short and to the point, maximum 2 sentences.

      <info>
      - Company name: ${companyName}
      </info>

      <message>
      ${message}
      </message>

      <output_classes>
      - OFFENSIVE: Content that includes hate speech, discriminatory language, insults, slurs, or harassment.
      - OFF_BRAND: Content that discusses competitors in a disparaging way.
      - VIOLENCE: Content that includes explicit threats, incitement of harm, or graphic descriptions of physical injury or violence.
      - NONE: If no other classes are appropriate and the message is fine.
      </output_classes>
      `,
    },
  ];

  const response = await fetch('/api/moderate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: message }),
  });

  if (!response.ok) {
    console.warn('Server returned an error:', response);
    return Promise.reject('Error with runGuardrailClassifier.');
  }

  const data = await response.json();
  // Map simple moderation decision to GuardrailOutput
  const flagged = data?.allowed === false;
  const category = flagged ? 'OFFENSIVE' : 'NONE';
  const output = {
    moderationRationale: 'server-moderation',
    moderationCategory: category,
    testText: message,
  };
  return GuardrailOutputZod.parse(output);
}

export interface RealtimeOutputGuardrailResult {
  tripwireTriggered: boolean;
  outputInfo: any;
}

export interface RealtimeOutputGuardrailArgs {
  agentOutput: string;
  agent?: any;
  context?: any;
}

export function createModerationGuardrail(companyName: string) {
  return {
    name: 'moderation_guardrail',

    async execute({
      agentOutput,
    }: RealtimeOutputGuardrailArgs): Promise<RealtimeOutputGuardrailResult> {
      try {
        const res = await runGuardrailClassifier(agentOutput, companyName);
        const triggered = res.moderationCategory !== 'NONE';
        return {
          tripwireTriggered: triggered,
          outputInfo: res,
        };
      } catch {
        return {
          tripwireTriggered: false,
          outputInfo: { error: 'guardrail_failed' },
        };
      }
    },
  } as const;
}
