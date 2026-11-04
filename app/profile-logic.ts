// Pure profile logic: option lists, cleaning and validation. No React, no imports, so it can be tested with plain Node.

/** Country name and its phone dialling code. The names are what job sites use, and what the agent compares. */
export const COUNTRY_TABLE: [string, string][] = [
  ['Afghanistan','+93'],['Albania','+355'],['Algeria','+213'],['Andorra','+376'],['Angola','+244'],['Antigua and Barbuda','+1'],['Argentina','+54'],['Armenia','+374'],
  ['Australia','+61'],['Austria','+43'],['Azerbaijan','+994'],['Bahamas','+1'],['Bahrain','+973'],['Bangladesh','+880'],['Barbados','+1'],['Belarus','+375'],['Belgium','+32'],
  ['Belize','+501'],['Benin','+229'],['Bhutan','+975'],['Bolivia','+591'],['Bosnia and Herzegovina','+387'],['Botswana','+267'],['Brazil','+55'],['Brunei','+673'],['Bulgaria','+359'],
  ['Burkina Faso','+226'],['Burundi','+257'],['Cambodia','+855'],['Cameroon','+237'],['Canada','+1'],['Cape Verde','+238'],['Central African Republic','+236'],['Chad','+235'],
  ['Chile','+56'],['China','+86'],['Colombia','+57'],['Comoros','+269'],['Congo','+242'],['Costa Rica','+506'],['Croatia','+385'],['Cuba','+53'],['Cyprus','+357'],
  ['Czech Republic','+420'],['Democratic Republic of the Congo','+243'],['Denmark','+45'],['Djibouti','+253'],['Dominica','+1'],['Dominican Republic','+1'],['Ecuador','+593'],
  ['Egypt','+20'],['El Salvador','+503'],['Equatorial Guinea','+240'],['Eritrea','+291'],['Estonia','+372'],['Eswatini','+268'],['Ethiopia','+251'],['Fiji','+679'],
  ['Finland','+358'],['France','+33'],['Gabon','+241'],['Gambia','+220'],['Georgia','+995'],['Germany','+49'],['Ghana','+233'],['Greece','+30'],['Grenada','+1'],
  ['Guatemala','+502'],['Guinea','+224'],['Guinea-Bissau','+245'],['Guyana','+592'],['Haiti','+509'],['Honduras','+504'],['Hong Kong','+852'],['Hungary','+36'],
  ['Iceland','+354'],['India','+91'],['Indonesia','+62'],['Iran','+98'],['Iraq','+964'],['Ireland','+353'],['Israel','+972'],['Italy','+39'],['Ivory Coast','+225'],
  ['Jamaica','+1'],['Japan','+81'],['Jordan','+962'],['Kazakhstan','+7'],['Kenya','+254'],['Kiribati','+686'],['Kosovo','+383'],['Kuwait','+965'],['Kyrgyzstan','+996'],
  ['Laos','+856'],['Latvia','+371'],['Lebanon','+961'],['Lesotho','+266'],['Liberia','+231'],['Libya','+218'],['Liechtenstein','+423'],['Lithuania','+370'],['Luxembourg','+352'],
  ['Macau','+853'],['Madagascar','+261'],['Malawi','+265'],['Malaysia','+60'],['Maldives','+960'],['Mali','+223'],['Malta','+356'],['Marshall Islands','+692'],['Mauritania','+222'],
  ['Mauritius','+230'],['Mexico','+52'],['Micronesia','+691'],['Moldova','+373'],['Monaco','+377'],['Mongolia','+976'],['Montenegro','+382'],['Morocco','+212'],['Mozambique','+258'],
  ['Myanmar','+95'],['Namibia','+264'],['Nauru','+674'],['Nepal','+977'],['Netherlands','+31'],['New Zealand','+64'],['Nicaragua','+505'],['Niger','+227'],['Nigeria','+234'],
  ['North Korea','+850'],['North Macedonia','+389'],['Norway','+47'],['Oman','+968'],['Pakistan','+92'],['Palau','+680'],['Palestine','+970'],['Panama','+507'],
  ['Papua New Guinea','+675'],['Paraguay','+595'],['Peru','+51'],['Philippines','+63'],['Poland','+48'],['Portugal','+351'],['Puerto Rico','+1'],['Qatar','+974'],['Romania','+40'],
  ['Russia','+7'],['Rwanda','+250'],['Saint Kitts and Nevis','+1'],['Saint Lucia','+1'],['Saint Vincent and the Grenadines','+1'],['Samoa','+685'],['San Marino','+378'],
  ['Sao Tome and Principe','+239'],['Saudi Arabia','+966'],['Senegal','+221'],['Serbia','+381'],['Seychelles','+248'],['Sierra Leone','+232'],['Singapore','+65'],['Slovakia','+421'],
  ['Slovenia','+386'],['Solomon Islands','+677'],['Somalia','+252'],['South Africa','+27'],['South Korea','+82'],['South Sudan','+211'],['Spain','+34'],['Sri Lanka','+94'],
  ['Sudan','+249'],['Suriname','+597'],['Sweden','+46'],['Switzerland','+41'],['Syria','+963'],['Taiwan','+886'],['Tajikistan','+992'],['Tanzania','+255'],['Thailand','+66'],
  ['Timor-Leste','+670'],['Togo','+228'],['Tonga','+676'],['Trinidad and Tobago','+1'],['Tunisia','+216'],['Turkey','+90'],['Turkmenistan','+993'],['Tuvalu','+688'],['Uganda','+256'],
  ['Ukraine','+380'],['United Arab Emirates','+971'],['United Kingdom','+44'],['United States','+1'],['Uruguay','+598'],['Uzbekistan','+998'],['Vanuatu','+678'],
  ['Vatican City','+379'],['Venezuela','+58'],['Vietnam','+84'],['Yemen','+967'],['Zambia','+260'],['Zimbabwe','+263'],
];
export const COUNTRIES: string[] = COUNTRY_TABLE.map(([name]) => name);
export const DIAL_CODES: Record<string, string> = Object.fromEntries(COUNTRY_TABLE);
/** Countries people most often apply in come first in the picker. */
export const TOP_COUNTRIES = ['India','United States','United Kingdom','Canada','Australia','Germany','Singapore','United Arab Emirates'];

const COUNTRY_ALIASES: Record<string, string> = {
  usa: 'United States', us: 'United States', 'u.s.': 'United States', 'u.s.a.': 'United States', america: 'United States', 'united states of america': 'United States',
  uk: 'United Kingdom', 'u.k.': 'United Kingdom', 'great britain': 'United Kingdom', england: 'United Kingdom', britain: 'United Kingdom',
  uae: 'United Arab Emirates', korea: 'South Korea', 'republic of korea': 'South Korea', czechia: 'Czech Republic', 'türkiye': 'Turkey', turkiye: 'Turkey',
  'russian federation': 'Russia', 'viet nam': 'Vietnam', burma: 'Myanmar', 'cote d\'ivoire': 'Ivory Coast', 'republic of india': 'India',
};
/** The canonical country name for whatever was typed or saved earlier ('india', 'USA'), or null when it is not a country. */
export function normalizeCountry(input: string): string | null {
  const text = (input || '').trim().toLowerCase();
  if (!text) return null;
  const exact = COUNTRIES.find(name => name.toLowerCase() === text);
  return exact || COUNTRY_ALIASES[text] || null;
}

export const CURRENCIES: [string, string][] = [
  ['INR','Indian rupee (₹)'],['USD','US dollar ($)'],['EUR','Euro (€)'],['GBP','British pound (£)'],['AED','UAE dirham'],['SGD','Singapore dollar'],['AUD','Australian dollar'],
  ['CAD','Canadian dollar'],['JPY','Japanese yen'],['CNY','Chinese yuan'],['CHF','Swiss franc'],['SEK','Swedish krona'],['NOK','Norwegian krone'],['DKK','Danish krone'],
  ['PLN','Polish zloty'],['ZAR','South African rand'],['BRL','Brazilian real'],['MXN','Mexican peso'],['PKR','Pakistani rupee'],['BDT','Bangladeshi taka'],['LKR','Sri Lankan rupee'],
  ['NPR','Nepalese rupee'],['PHP','Philippine peso'],['IDR','Indonesian rupiah'],['MYR','Malaysian ringgit'],['THB','Thai baht'],['VND','Vietnamese dong'],['KRW','South Korean won'],
  ['SAR','Saudi riyal'],['QAR','Qatari riyal'],['NGN','Nigerian naira'],['KES','Kenyan shilling'],['EGP','Egyptian pound'],['TRY','Turkish lira'],['NZD','New Zealand dollar'],['HKD','Hong Kong dollar'],
];
const CURRENCY_BY_COUNTRY: Record<string, string> = {
  India:'INR','United States':'USD','United Kingdom':'GBP',Canada:'CAD',Australia:'AUD',Germany:'EUR',France:'EUR',Italy:'EUR',Spain:'EUR',Netherlands:'EUR',Ireland:'EUR',
  Singapore:'SGD','United Arab Emirates':'AED',Japan:'JPY',China:'CNY',Switzerland:'CHF',Sweden:'SEK',Norway:'NOK',Denmark:'DKK',Poland:'PLN','South Africa':'ZAR',Brazil:'BRL',
  Mexico:'MXN',Pakistan:'PKR',Bangladesh:'BDT','Sri Lanka':'LKR',Nepal:'NPR',Philippines:'PHP',Indonesia:'IDR',Malaysia:'MYR',Thailand:'THB',Vietnam:'VND','South Korea':'KRW',
  'Saudi Arabia':'SAR',Qatar:'QAR',Nigeria:'NGN',Kenya:'KES',Egypt:'EGP',Turkey:'TRY','New Zealand':'NZD','Hong Kong':'HKD',
};
export function defaultCurrency(country: string): string {
  return CURRENCY_BY_COUNTRY[normalizeCountry(country) || ''] || 'USD';
}

export const NOTICE_PERIODS = ['Immediately', '15 days', '30 days', '60 days', '90 days', 'More than 90 days'];
export const START_OPTIONS = ['Immediately', 'Within 2 weeks', 'Within 1 month', 'Within 2 months', 'Within 3 months'];
export const DEGREES = ['High school', 'Diploma', 'Associate degree', 'Bachelor’s degree', 'Master’s degree', 'Doctorate', 'Certificate', 'Other'];
export const ELIGIBILITY = ['Citizen', 'Permanent resident', 'Valid work visa / permit', 'Need work authorization', 'Other'];
export const LEVELS = ['Intern', 'Fresher', 'Experienced'];

export const ROLE_SUGGESTIONS = ['AI Engineer', 'Machine Learning Engineer', 'Generative AI Engineer', 'Data Scientist', 'Data Analyst', 'Python Developer', 'Software Engineer',
  'Full Stack Developer', 'Backend Developer', 'Frontend Developer', 'DevOps Engineer', 'Cloud Engineer', 'QA Engineer', 'Product Manager', 'UI/UX Designer', 'Business Analyst'];
export const SKILL_SUGGESTIONS = ['Python', 'JavaScript', 'TypeScript', 'Java', 'C++', 'SQL', 'React', 'Node.js', 'FastAPI', 'Django', 'Flask', 'Machine Learning', 'Deep Learning', 'NLP',
  'LangChain', 'TensorFlow', 'PyTorch', 'Pandas', 'NumPy', 'Scikit-learn', 'Docker', 'Kubernetes', 'AWS', 'Git', 'Linux', 'MongoDB', 'PostgreSQL', 'REST APIs', 'HTML', 'CSS'];
const CITY_SUGGESTIONS: Record<string, string[]> = {
  India: ['Hyderabad', 'Bengaluru', 'Pune', 'Chennai', 'Mumbai', 'Delhi NCR', 'Gurugram', 'Noida', 'Kolkata', 'Ahmedabad', 'Kochi', 'Remote'],
  'United States': ['New York', 'San Francisco', 'Seattle', 'Austin', 'Boston', 'Chicago', 'Los Angeles', 'Remote'],
  'United Kingdom': ['London', 'Manchester', 'Edinburgh', 'Birmingham', 'Remote'],
  Canada: ['Toronto', 'Vancouver', 'Montreal', 'Ottawa', 'Remote'],
  Australia: ['Sydney', 'Melbourne', 'Brisbane', 'Perth', 'Remote'],
  Germany: ['Berlin', 'Munich', 'Hamburg', 'Frankfurt', 'Remote'],
  Singapore: ['Singapore', 'Remote'],
  'United Arab Emirates': ['Dubai', 'Abu Dhabi', 'Remote'],
};
export function citySuggestions(country: string): string[] {
  return CITY_SUGGESTIONS[normalizeCountry(country) || ''] || ['Remote'];
}

// ---- lists ------------------------------------------------------------------------------------------------
/** "a, b; c" to a tidy list, without empties or repeats. */
export function splitList(text: string): string[] {
  const seen = new Set<string>(), out: string[] = [];
  for (const part of (text || '').split(/[,;\n|]+/)) {
    const item = part.trim();
    if (item && !seen.has(item.toLowerCase())) { seen.add(item.toLowerCase()); out.push(item); }
  }
  return out;
}
export const joinList = (items: string[]): string => items.join(', ');

/** Skills from a pasted resume section: drops "Frontend:"-style category labels, bullets, empties and repeats. */
export function parseSkillList(text: string): string[] {
  const out: string[] = [], seen = new Set<string>();
  for (const raw of (text || '').split(/[\n;|]+|,(?![^(]*\))/)) {
    let item = raw.trim().replace(/^(?:skills?|technical skills|competencies)\s*:?\s*/i, '');
    const labelled = item.match(/^[A-Za-z][A-Za-z &/+.-]{1,40}:\s*(.+)$/);
    if (labelled) item = labelled[1];
    item = item.replace(/^[-•·*\s]+/, '').replace(/[-•·*\s.,;:]+$/, '').trim();
    if (!item || item.length > 60 || seen.has(item.toLowerCase())) continue;
    seen.add(item.toLowerCase()); out.push(item);
  }
  return out;
}
/** True when a saved skills string is a pasted blob rather than a clean comma list. */
export function skillsLookMessy(text: string): boolean {
  const t = text || '';
  return /^\s*,/.test(t) || /[|;\n]/.test(t) || /\b[A-Za-z][A-Za-z &/+.-]{1,40}:\s/.test(t) || /,\s*,/.test(t);
}

// ---- phone ------------------------------------------------------------------------------------------------
/** One entry per dialling code, labelled with the countries that use it (the busiest ones first for +1 and +7). */
export const PHONE_CODES: [string, string][] = (() => {
  const byCode = new Map<string, string[]>();
  for (const [name, code] of COUNTRY_TABLE) byCode.set(code, [...(byCode.get(code) || []), name]);
  const first: Record<string, string[]> = { '+1': ['United States', 'Canada'], '+7': ['Russia', 'Kazakhstan'] };
  return [...byCode.entries()]
    .sort((a, b) => Number(a[0].slice(1)) - Number(b[0].slice(1)))
    .map(([code, names]) => {
      const ordered = [...(first[code] || []).filter(n => names.includes(n)), ...names.filter(n => !(first[code] || []).includes(n))];
      return [code, `${code}  ${ordered.slice(0, 2).join(', ')}${ordered.length > 2 ? '…' : ''}`] as [string, string];
    });
})();
/** '+91 6303391412' to {code:'+91', number:'6303391412'}. Numbers without a code keep the fallback code. */
export function splitPhone(phone: string, fallbackCode: string): { code: string; number: string } {
  const text = (phone || '').trim();
  const match = text.match(/^\+(\d{1,3})[\s-]*(.*)$/);
  if (!match) return { code: fallbackCode, number: text };
  const known = new Set(Object.values(DIAL_CODES));
  for (const length of [3, 2, 1]) {
    const code = '+' + match[1].slice(0, length);
    if (known.has(code)) return { code, number: (match[1].slice(length) + match[2]).trim() };
  }
  return { code: '+' + match[1], number: match[2].trim() };
}
export const joinPhone = (code: string, number: string): string => (number.trim() ? `${code} ${number.trim()}` : '');
export function phoneProblem(phone: string): string {
  const digits = (phone || '').replace(/\D/g, '');
  if (!digits) return 'Enter your mobile number.';
  const { number } = splitPhone(phone, '');
  const nationalDigits = number.replace(/\D/g, '');
  if (nationalDigits.length < 6 || nationalDigits.length > 13) return 'Enter a valid mobile number, without the country code.';
  return '';
}

// ---- dates ------------------------------------------------------------------------------------------------
export function startDateProblem(value: string, today: Date): string {
  if (!value) return 'Choose when you can start.';
  if (START_OPTIONS.includes(value)) return '';
  const date = new Date(value + 'T00:00:00');
  if (isNaN(date.getTime())) return 'Choose when you can start.';
  const floor = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return date < floor ? 'This date has passed. Choose when you can start.' : '';
}

// ---- eligibility text -------------------------------------------------------------------------------------
export function authorizationText(eligibility: string, country: string): string {
  const place = normalizeCountry(country) || country || 'the target country';
  if (eligibility === 'Citizen') return `Citizen of ${place}, authorized to work without sponsorship`;
  if (eligibility === 'Permanent resident') return `Permanent resident of ${place}, authorized to work`;
  if (eligibility === 'Valid work visa / permit') return `Holds a valid work visa or permit for ${place}`;
  if (eligibility === 'Need work authorization') return `Requires work authorization to work in ${place}`;
  return '';
}

// ---- validation -------------------------------------------------------------------------------------------
export type Errors = Record<string, string>;
export type ProfileLike = {
  name: string; email: string; phone: string; address: string; resume_text: string; portfolio: string;
  career_level: string; education: { degree: string; school: string; year: string; major: string }[];
  work_history: { title: string; company: string; start: string; end: string; current: boolean; responsibilities: string }[];
  no_experience: boolean; experience: number;
  roles: string; country: string; locations: string; skills: string; work_modes: string[]; employment_type: string; availability: string; relocation: string; salary: string;
  eligibility: string; sponsorship: string; authorization: string; age_confirmed: boolean;
};
/** Human names for every validated field, so messages never show raw keys like 'resume_text'. */
export const FIELD_LABELS: Record<string, string> = {
  name: 'Full name', email: 'Email address', phone: 'Mobile number', address: 'Address', resume_text: 'Resume', portfolio: 'Portfolio URL',
  career_level: 'Career stage', education: 'Education', work_history: 'Work experience', experience: 'Years of experience', roles: 'Desired positions', country: 'Target country',
  locations: 'Preferred locations', skills: 'Skills', work_modes: 'Work mode', employment_type: 'Employment type', availability: 'Start date', relocation: 'Relocation',
  salary: 'Expected salary', eligibility: 'Work eligibility', sponsorship: 'Visa sponsorship', authorization: 'Work authorization statement', age_confirmed: 'Working age confirmation',
};

export function validateStep(p: ProfileLike, step: number, today: Date = new Date()): Errors {
  const e: Errors = {};
  if (step === 0) {
    if ((p.name || '').trim().length < 2) e.name = 'Enter your full name.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test((p.email || '').trim())) e.email = 'Enter a valid email address, like name@example.com.';
    const phone = phoneProblem(p.phone); if (phone) e.phone = phone;
    if (p.portfolio && !/^https?:\/\/\S+\.\S+/i.test(p.portfolio.trim())) e.portfolio = 'Start the link with https://';
    if ((p.address || '').trim().length < 8) e.address = 'Enter your address: street, city, state and postal code.';
    if ((p.resume_text || '').trim().length < 50) e.resume_text = 'Upload your resume, or paste its text.';
  }
  if (step === 1) {
    if (!p.career_level) e.career_level = 'Choose the option that describes you best.';
    if (!p.education.length) e.education = 'Add at least one education entry.';
    p.education.forEach((row, i) => {
      if (!row.degree) e[`education.${i}.degree`] = 'Choose a degree.';
      if (!row.school.trim()) e[`education.${i}.school`] = 'Enter the school or college name.';
      if (!row.year) e[`education.${i}.year`] = 'Choose the graduation year.';
      if (!row.major.trim()) e[`education.${i}.major`] = 'Enter your field of study.';
    });
    const needsWork = p.career_level === 'Experienced' && !p.no_experience;
    if (needsWork && !p.work_history.length) e.work_history = 'Add your work experience.';
    p.work_history.forEach((row, i) => {
      if (!row.title.trim()) e[`work.${i}.title`] = 'Enter the job title.';
      if (!row.company.trim()) e[`work.${i}.company`] = 'Enter the company name.';
      if (!row.start) e[`work.${i}.start`] = 'Choose the start month.';
      if (!row.current && !row.end) e[`work.${i}.end`] = 'Choose the end month, or tick “I currently work here”.';
      if (row.end && row.start && row.start > row.end) e[`work.${i}.end`] = 'The end date must be after the start date.';
      if (!row.responsibilities.trim()) e[`work.${i}.responsibilities`] = 'Describe what you did.';
    });
    if (p.career_level === 'Experienced' && !(p.experience > 0)) e.experience = 'Enter your total years of experience.';
  }
  if (step === 2) {
    if (!splitList(p.roles).length) e.roles = 'Add at least one position you want.';
    if (!p.country) e.country = 'Choose your target country.';
    else if (!normalizeCountry(p.country)) e.country = 'Choose a country from the list.';
    if (!splitList(p.locations).length) e.locations = 'Add at least one city (or “Remote”).';
    if (!parseSkillList(p.skills).length) e.skills = 'Add your skills.';
    if (!p.work_modes.length) e.work_modes = 'Choose at least one work mode.';
    if (!p.employment_type) e.employment_type = 'Choose an employment type.';
    const start = startDateProblem(p.availability, today); if (start) e.availability = start;
    if (!p.relocation) e.relocation = 'Choose an option.';
    if (p.salary && !(Number(p.salary) >= 0)) e.salary = 'Enter numbers only, like 500000.';
  }
  if (step === 3) {
    if (!p.eligibility) e.eligibility = 'Choose your work status in the target country.';
    if (!p.sponsorship) e.sponsorship = 'Choose Yes or No.';
    if (!(p.authorization || '').trim()) e.authorization = 'Enter your work authorization statement.';
    if (!p.age_confirmed) e.age_confirmed = 'Confirm that you meet the minimum working age.';
  }
  return e;
}
export function validateAll(p: ProfileLike, today: Date = new Date()): { step: number; errors: Errors }[] {
  return [0, 1, 2, 3].map(step => ({ step, errors: validateStep(p, step, today) })).filter(x => Object.keys(x.errors).length);
}
/** A consistency warning that is not an error: the answers contradict each other. */
export function sponsorshipWarning(p: Pick<ProfileLike, 'eligibility' | 'sponsorship' | 'country'>): string {
  if (p.sponsorship === 'Yes' && (p.eligibility === 'Citizen' || p.eligibility === 'Permanent resident'))
    return `You are a ${p.eligibility.toLowerCase()} of ${p.country || 'this country'} but said you need sponsorship. Most applications should say No; check this.`;
  if (p.sponsorship === 'No' && p.eligibility === 'Need work authorization')
    return 'You said you need work authorization but no sponsorship. Check that these match.';
  return '';
}
export const graduationYears = (now: Date): string[] => {
  const out: string[] = [];
  for (let y = now.getFullYear() + 6; y >= 1970; y--) out.push(String(y));
  return out;
};

// ---- common application questions ----------------------------------------------------------------------------
/** Yes/No questions job forms ask over and over. The person answers once here; the agent never guesses them. */
export const COMMON_QUESTIONS = [
  { id: 'background', question: 'Are you willing to undergo a background check?' },
  { id: 'drugtest', question: 'Are you willing to undergo a drug test?' },
  { id: 'onsite', question: 'Are you comfortable working on-site and commuting to the job location?' },
  { id: 'shifts', question: 'Are you willing to work night or rotational shifts?' },
  { id: 'laptop', question: 'Do you have a laptop and a reliable internet connection?' },
  { id: 'bond', question: 'Are you willing to sign a service agreement or bond?' },
  { id: 'degree', question: 'Have you completed your Bachelor’s degree?' },
] as const;
export type CommonId = typeof COMMON_QUESTIONS[number]['id'];

const lineFor = (id: CommonId) => COMMON_QUESTIONS.find(q => q.id === id)!.question;
/** The Yes/No already saved for each common question, read from the approved-answers text. */
export function commonAnswers(screening: string): Partial<Record<CommonId, 'Yes' | 'No'>> {
  const out: Partial<Record<CommonId, 'Yes' | 'No'>> = {};
  for (const line of (screening || '').split(/\r?\n/)) {
    for (const q of COMMON_QUESTIONS) {
      if (line.trim().toLowerCase().startsWith(q.question.toLowerCase())) {
        const answer = line.trim().slice(q.question.length).trim().toLowerCase().replace(/[.!]+$/, '');
        if (answer === 'yes' || answer === 'no') out[q.id] = answer === 'yes' ? 'Yes' : 'No';
      }
    }
  }
  return out;
}
/** Set (or with '' remove) one common answer, leaving every other line of the approved answers untouched. */
export function setCommonAnswer(screening: string, id: CommonId, answer: 'Yes' | 'No' | ''): string {
  const question = lineFor(id).toLowerCase();
  const kept = (screening || '').split(/\r?\n/).filter(line => !line.trim().toLowerCase().startsWith(question));
  while (kept.length && !kept[kept.length - 1].trim()) kept.pop();
  if (answer) kept.push(`${lineFor(id)} ${answer}`);
  return kept.join('\n');
}
