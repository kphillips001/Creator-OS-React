export type NormalizedXAccount = { username: string | null; error: string | null };
const USERNAME = /^[A-Za-z0-9_]{1,15}$/;
const MARKDOWN_LINK = /^\[(https?:\/\/[^\]]+)]\((https?:\/\/[^)]+)\)$/i;

export function normalizeXAccount(rawValue: string): NormalizedXAccount {
  let value = rawValue.trim();
  if (!value) return { username: null, error: null };
  const markdown = value.match(MARKDOWN_LINK);
  if (markdown) value = markdown[2]!;
  let candidate = value;
  if (/^https?:\/\//i.test(value)) {
    let url: URL;
    try { url = new URL(value); } catch { return { username:null,error:"Enter a valid X username or profile URL." }; }
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    if (host!=="x.com"&&host!=="twitter.com") return { username:null,error:"Profile URLs must use x.com or twitter.com." };
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts.length!==1) return { username:null,error:"Enter an X profile URL, not a post or nested URL." };
    candidate = parts[0]!;
  } else if (candidate.startsWith("@")) candidate = candidate.slice(1);
  if (!USERNAME.test(candidate)) return { username:null,error:"Usernames must contain 1–15 letters, numbers, or underscores." };
  return { username:candidate,error:null };
}

export function parseXAccountBatch(rawValue: string) {
  const usernames:string[]=[]; const invalid:Array<{line:number;value:string;error:string}>=[]; const seen=new Set<string>();
  rawValue.split(/\r?\n/).forEach((rawLine,index)=>{const value=rawLine.trim();if(!value)return;const result=normalizeXAccount(value);if(!result.username){invalid.push({line:index+1,value,error:result.error??"Invalid X account."});return;}const identity=result.username.toLowerCase();if(seen.has(identity))return;seen.add(identity);usernames.push(result.username);});
  return { usernames, invalid };
}
