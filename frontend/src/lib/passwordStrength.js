// passwordStrength.js
// --------------------
// Lightweight, dependency-free password strength scoring. Not a substitute
// for a proper library like zxcvbn if you want more accurate entropy
// estimation later -- this is a simple heuristic: character variety +
// length + a common-password/pattern blocklist, which is enough to catch
// the obvious weak cases (short, all-lowercase, "password123", etc.)
// without shipping a large extra dependency.

// A short list of extremely common passwords / patterns worth calling out
// explicitly, regardless of how they score on length/variety alone.
const COMMON_PASSWORDS = new Set([
  "password", "password1", "password123", "123456", "12345678", "123456789",
  "qwerty", "qwerty123", "letmein", "welcome", "admin", "admin123",
  "iloveyou", "abc123", "111111", "123123", "000000", "1234567890",
  "monkey", "dragon", "football", "baseball", "trustno1",
]);

/**
 * @param {string} pw
 * @returns {{ score: 0|1|2|3, label: "Weak"|"Fair"|"Good"|"Strong", feedback: string[] }}
 */
export function scorePasswordStrength(pw) {
  const feedback = [];
  if (!pw) return { score: 0, label: "Weak", feedback: ["Enter a password"] };

  const lower = pw.toLowerCase();
  if (COMMON_PASSWORDS.has(lower)) {
    return { score: 0, label: "Weak", feedback: ["This is one of the most commonly used passwords -- easy to guess"] };
  }

  let points = 0;

  // Length is the single strongest predictor of crack resistance.
  if (pw.length >= 8) points += 1;
  if (pw.length >= 12) points += 1;
  if (pw.length < 8) feedback.push("Use at least 8 characters (12+ is better)");

  // Character variety.
  const hasLower = /[a-z]/.test(pw);
  const hasUpper = /[A-Z]/.test(pw);
  const hasDigit = /\d/.test(pw);
  const hasSymbol = /[^a-zA-Z0-9]/.test(pw);
  const varietyCount = [hasLower, hasUpper, hasDigit, hasSymbol].filter(Boolean).length;
  if (varietyCount >= 3) points += 1;
  if (varietyCount === 4) points += 1;
  if (!hasUpper) feedback.push("Add an uppercase letter");
  if (!hasDigit) feedback.push("Add a number");
  if (!hasSymbol) feedback.push("Add a symbol (e.g. ! @ # $)");

  // Obvious sequential/repeated patterns knock points back down.
  const hasRepeat = /(.)\1{2,}/.test(pw); // aaa, 111
  const hasSequence = /(?:012|123|234|345|456|567|678|789|890|abc|bcd|cde|qwe|wer|asd|sdf)/i.test(pw);
  if (hasRepeat || hasSequence) {
    points = Math.max(0, points - 1);
    feedback.push("Avoid repeated or sequential characters (e.g. \"aaa\", \"123\")");
  }

  const score = Math.max(0, Math.min(3, points));
  const label = ["Weak", "Fair", "Good", "Strong"][score];
  return { score, label, feedback };
}