/**
 * Renders one question group, for every IELTS question type.
 *
 * The whole design rests on one idea: a completion layout is text with
 * {{Qn}} placeholders in it. Split on that token and every completion type -
 * notes, tables, forms, flow-charts, summaries, sentences - renders with the
 * same component, whether the blank sits in a table cell, a bullet or a caption.
 *
 * `readOnly` drives the results screen too, so a candidate reviews the exact
 * layout they answered rather than a second, subtly different renderer.
 */
import { ReactNode } from 'react';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { AnswerValue, ExamGroup, LayoutBlock, Option } from '@/lib/exams';

const PLACEHOLDER = /\{\{Q(\d+)\}\}/g;

/** Max words allowed, from the rubric. Used to stop over-long typing. */
const WORD_LIMITS: Record<string, number> = {
  one_word: 1, one_word_number: 2,
  two_words: 2, two_words_number: 3,
  three_words: 3, three_words_number: 4,
};

const WORD_LIMIT_LABELS: Record<string, string> = {
  one_word: 'ONE WORD ONLY',
  one_word_number: 'ONE WORD AND/OR A NUMBER',
  two_words: 'NO MORE THAN TWO WORDS',
  two_words_number: 'NO MORE THAN TWO WORDS AND/OR A NUMBER',
  three_words: 'NO MORE THAN THREE WORDS',
  three_words_number: 'NO MORE THAN THREE WORDS AND/OR A NUMBER',
};

export interface GroupRendererProps {
  group: ExamGroup;
  answers: Record<number, AnswerValue>;
  onChange: (questionNumber: number, value: AnswerValue) => void;
  readOnly?: boolean;
  /** Results view: per-question correctness. */
  marks?: Record<number, { is_correct: boolean; accepted: string[]; reason: string }>;
  onFocusQuestion?: (questionNumber: number) => void;
}

function textOf(value: AnswerValue | undefined): string {
  if (!value) return '';
  if ('text' in value) return value.text ?? '';
  if ('letter' in value) return value.letter ?? '';
  if ('letters' in value) return (value.letters ?? []).join(', ');
  return '';
}

function lettersOf(value: AnswerValue | undefined): string[] {
  if (value && 'letters' in value) return value.letters ?? [];
  if (value && 'letter' in value && value.letter) return [value.letter];
  return [];
}

function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

/** One inline blank. */
function GapInput({
  number, group, answers, onChange, readOnly, marks, onFocusQuestion,
}: GroupRendererProps & { number: number }) {
  const value = textOf(answers[number]);
  const limit = WORD_LIMITS[group.word_limit];
  const over = limit !== undefined && countWords(value) > limit;
  const mark = marks?.[number];

  const width = !limit || limit <= 1 ? 'w-32' : limit === 2 ? 'w-44' : 'w-56';

  return (
    <span className="inline-flex items-baseline gap-1 align-baseline mx-1">
      <sup className="text-[10px] font-semibold text-muted-foreground">{number}</sup>
      <Input
        value={value}
        readOnly={readOnly}
        onFocus={() => onFocusQuestion?.(number)}
        onChange={(event) => onChange(number, { text: event.target.value })}
        aria-label={`Question ${number}`}
        // Spellcheck off matters: red squiggles would flag exactly the spelling
        // errors IELTS penalises, handing the candidate a free correction.
        spellCheck={false}
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="off"
        className={cn(
          'h-8 inline-block px-2 py-0 text-sm', width,
          over && 'ring-2 ring-amber-400',
          mark && (mark.is_correct
            ? 'ring-2 ring-emerald-500 bg-emerald-50 dark:bg-emerald-950'
            : 'ring-2 ring-red-400 bg-red-50 dark:bg-red-950'),
        )}
      />
      {over && !readOnly && (
        <span className="text-[10px] text-amber-600">
          {WORD_LIMIT_LABELS[group.word_limit]}
        </span>
      )}
    </span>
  );
}

/** Split text on {{Qn}} and interleave inputs. One regex, one component. */
function withGaps(text: string, props: GroupRendererProps): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  PLACEHOLDER.lastIndex = 0;
  while ((match = PLACEHOLDER.exec(text)) !== null) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const number = Number(match[1]);
    nodes.push(<GapInput key={`q${number}`} number={number} {...props} />);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}

function LayoutBlocks({ blocks, props }: { blocks: LayoutBlock[]; props: GroupRendererProps }) {
  return (
    <div className="space-y-2">
      {blocks.map((block, index) => {
        if (block.kind === 'heading') {
          return <h4 key={index} className="font-semibold mt-3">{block.text}</h4>;
        }
        if (block.kind === 'bullets') {
          return (
            <ul key={index} className="list-disc pl-6 space-y-1">
              {block.items.map((item, i) => <li key={i}>{withGaps(item, props)}</li>)}
            </ul>
          );
        }
        if (block.kind === 'table') {
          return (
            <div key={index} className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                {block.head && (
                  <thead>
                    <tr>
                      {block.head.map((cell, i) => (
                        <th key={i} className="border p-2 text-left bg-muted">
                          {cell.text}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {block.rows.map((row, r) => (
                    <tr key={r}>
                      {row.map((cell, c) => (
                        <td key={c} className="border p-2 align-top">
                          {withGaps(cell.text, props)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.kind === 'flow') {
          return (
            <div key={index} className="space-y-1">
              {block.steps.map((step, i) => (
                <div key={i} className="flex flex-col items-center">
                  <div className="border rounded px-3 py-2 w-full text-center">
                    {withGaps(step.text, props)}
                  </div>
                  {i < block.steps.length - 1 && (
                    <span className="text-muted-foreground" aria-hidden>↓</span>
                  )}
                </div>
              ))}
            </div>
          );
        }
        return <p key={index} className="leading-7">{withGaps(block.text, props)}</p>;
      })}
    </div>
  );
}

function OptionBank({ options }: { options: Option[] }) {
  if (!options.length) return null;
  return (
    <Card className="p-3 bg-muted/40">
      <ul className="grid gap-1 sm:grid-cols-2">
        {options.map((option) => (
          <li key={option.letter} className="text-sm">
            <span className="font-semibold mr-2">{option.letter}</span>
            {option.text}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function ChoiceRow({
  number, choices, props, multi, selectCount,
}: {
  number: number; choices: Option[]; props: GroupRendererProps;
  multi?: boolean; selectCount?: number | null;
}) {
  const { answers, onChange, readOnly, marks, onFocusQuestion } = props;
  const mark = marks?.[number];
  const selected = lettersOf(answers[number]);

  if (multi) {
    const limit = selectCount ?? 2;
    return (
      <div className="space-y-1">
        {choices.map((choice) => {
          const checked = selected.includes(choice.letter);
          return (
            <label key={choice.letter} className="flex items-start gap-2 text-sm">
              <Checkbox
                checked={checked}
                disabled={readOnly || (!checked && selected.length >= limit)}
                onCheckedChange={(next) => {
                  const updated = next
                    ? [...selected, choice.letter]
                    : selected.filter((letter) => letter !== choice.letter);
                  onChange(number, { letters: updated });
                }}
              />
              <span><b className="mr-1">{choice.letter}</b>{choice.text}</span>
            </label>
          );
        })}
      </div>
    );
  }

  return (
    <RadioGroup
      value={selected[0] ?? ''}
      disabled={readOnly}
      onValueChange={(letter) => onChange(number, { letter })}
      className={cn(
        'space-y-1',
        mark && (mark.is_correct ? 'rounded ring-1 ring-emerald-500 p-2'
                                 : 'rounded ring-1 ring-red-400 p-2'),
      )}
      onFocus={() => onFocusQuestion?.(number)}
    >
      {choices.map((choice) => (
        <div key={choice.letter} className="flex items-start gap-2">
          <RadioGroupItem value={choice.letter} id={`q${number}${choice.letter}`} />
          <Label htmlFor={`q${number}${choice.letter}`} className="text-sm font-normal">
            <b className="mr-1">{choice.letter}</b>{choice.text}
          </Label>
        </div>
      ))}
    </RadioGroup>
  );
}

const TFNG_CHOICES: Option[] = [
  { letter: 'TRUE', text: 'The statement agrees with the information' },
  { letter: 'FALSE', text: 'The statement contradicts the information' },
  { letter: 'NOT GIVEN', text: 'There is no information on this' },
];

const YNNG_CHOICES: Option[] = [
  { letter: 'YES', text: "The statement agrees with the writer's views" },
  { letter: 'NO', text: "The statement contradicts the writer's views" },
  { letter: 'NOT GIVEN', text: "It is impossible to say what the writer thinks" },
];

export function GroupRenderer(props: GroupRendererProps) {
  const { group, answers, onChange, readOnly, marks, onFocusQuestion } = props;

  const body = (() => {
    switch (group.type) {
      case 'tfng':
      case 'ynng': {
        // The legend is rendered canonically rather than parsed out of the PDF:
        // it is typeset as two columns, so reading it pairs the wrong label with
        // the wrong definition.
        const choices = group.type === 'tfng' ? TFNG_CHOICES : YNNG_CHOICES;
        return (
          <div className="space-y-4">
            <Card className="p-3 bg-muted/40 text-xs space-y-1">
              {choices.map((choice) => (
                <div key={choice.letter}>
                  <b className="mr-2">{choice.letter}</b>{choice.text}
                </div>
              ))}
            </Card>
            {group.questions.map((question) => (
              <div key={question.number} className="space-y-1">
                <p className="text-sm">
                  <b className="mr-2">{question.number}</b>{question.prompt_text}
                </p>
                <ChoiceRow number={question.number} choices={choices} props={props} />
              </div>
            ))}
          </div>
        );
      }

      case 'mcq_single':
      case 'mcq_multi':
        return (
          <div className="space-y-4">
            {group.options.length > 0 && <OptionBank options={group.options} />}
            {group.questions.map((question) => (
              <div key={question.number} className="space-y-1">
                <p className="text-sm">
                  <b className="mr-2">{question.number}</b>{question.prompt_text}
                </p>
                <ChoiceRow
                  number={question.number}
                  choices={question.options.length ? question.options : group.options}
                  props={props}
                  multi={group.type === 'mcq_multi'}
                  selectCount={group.select_count}
                />
              </div>
            ))}
          </div>
        );

      case 'matching_bank':
      case 'matching_features':
      case 'matching_paragraph':
      case 'sentence_endings':
      case 'list_of_headings':
      case 'classification':
      case 'map_labelling':
      case 'plan_labelling':
      case 'diagram_labelling':
        return (
          <div className="space-y-4">
            {group.image_url && (
              <img
                src={group.image_url}
                alt="Figure for these questions"
                className="max-w-full rounded border"
              />
            )}
            {group.options.length > 0 && <OptionBank options={group.options} />}
            <div className="space-y-2">
              {group.questions.map((question) => {
                const mark = marks?.[question.number];
                return (
                  <div key={question.number} className="flex items-center gap-2 text-sm">
                    <b className="w-6 shrink-0">{question.number}</b>
                    <span className="flex-1">{question.prompt_text}</span>
                    <Input
                      value={textOf(answers[question.number])}
                      readOnly={readOnly}
                      onFocus={() => onFocusQuestion?.(question.number)}
                      onChange={(event) =>
                        onChange(question.number, {
                          letter: event.target.value.toUpperCase().slice(0, 2),
                        })}
                      aria-label={`Question ${question.number}`}
                      spellCheck={false}
                      autoComplete="off"
                      className={cn(
                        'h-8 w-16 text-center uppercase',
                        mark && (mark.is_correct
                          ? 'ring-2 ring-emerald-500' : 'ring-2 ring-red-400'),
                      )}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        );

      case 'unknown':
        return (
          <div className="space-y-3">
            <Badge variant="destructive">
              This question type was not recognised during import
            </Badge>
            <LayoutBlocks blocks={group.layout} props={props} />
          </div>
        );

      default:
        // Every completion type: notes, table, form, flow-chart, summary,
        // sentences, short answer.
        return (
          <div className="space-y-3">
            {group.image_url && (
              <img
                src={group.image_url}
                alt="Figure for these questions"
                className="max-w-full rounded border"
              />
            )}
            {group.options.length > 0 && <OptionBank options={group.options} />}
            <LayoutBlocks blocks={group.layout} props={props} />
          </div>
        );
    }
  })();

  return (
    <section className="space-y-3" data-group={group.id}>
      <header className="space-y-1">
        <h3 className="font-semibold">
          Questions {group.first_question}–{group.last_question}
        </h3>
        {group.instruction_text && (
          <p className="text-sm text-muted-foreground">{group.instruction_text}</p>
        )}
        {group.word_limit && (
          <Badge variant="secondary">{WORD_LIMIT_LABELS[group.word_limit]}</Badge>
        )}
      </header>
      {body}
    </section>
  );
}

export default GroupRenderer;
