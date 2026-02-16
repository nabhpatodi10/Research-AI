export const benchmarkSystems = [
  {
    name: 'ResearchAI',
    overall: 55.32,
    comprehensiveness: 55.95,
    insight: 59.3,
    instructionFollowing: 52.08,
    readability: 52.53,
  },
  {
    name: 'Onyx DeepResearch',
    overall: 54.54,
    comprehensiveness: 54.67,
    insight: 56.43,
    instructionFollowing: 53.08,
    readability: 52.02,
  },
  {
    name: 'Qianfan DeepResearch Pro',
    overall: 54.22,
    comprehensiveness: 55.07,
    insight: 56.09,
    instructionFollowing: 51.77,
    readability: 52.12,
  },
  {
    name: 'Tavily Research',
    overall: 52.44,
    comprehensiveness: 52.84,
    insight: 53.59,
    instructionFollowing: 51.92,
    readability: 49.21,
  },
  {
    name: 'Salesforce Air DeepResearch',
    overall: 50.65,
    comprehensiveness: 50.0,
    insight: 51.09,
    instructionFollowing: 50.77,
    readability: 50.32,
  },
  {
    name: 'LangChain DeepResearch (GPT-5 + Tavily)',
    overall: 49.33,
    comprehensiveness: 49.8,
    insight: 47.34,
    instructionFollowing: 51.05,
    readability: 48.99,
  },
  {
    name: 'Gemini DeepResearch (2.5 Pro)',
    overall: 49.71,
    comprehensiveness: 49.51,
    insight: 49.45,
    instructionFollowing: 50.12,
    readability: 50.0,
  },
  {
    name: 'OpenAI DeepResearch (o3)',
    overall: 46.45,
    comprehensiveness: 46.46,
    insight: 43.73,
    instructionFollowing: 49.39,
    readability: 47.22,
  },
];

export const parameterSeries = [
  { key: 'comprehensiveness', label: 'Comprehensiveness', color: '#1d4ed8' },
  { key: 'insight', label: 'Insight', color: '#0284c7' },
  { key: 'instructionFollowing', label: 'Instruction Following', color: '#0ea5e9' },
  { key: 'readability', label: 'Readability', color: '#14b8a6' },
];

export const chartTicks = [0, 10, 20, 30, 40, 50, 60];
export const maxScore = 65;
