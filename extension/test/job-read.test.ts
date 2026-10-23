// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { pageUrl, readJob } from "../src/job-read";

const URL = "https://careers.example/jobs/123?utm_source=email&token=secret#apply";
const JD = "Build Ruby on Rails services and maintain PostgreSQL databases. ".repeat(4);

describe("reading public job adverts", () => {
  it("reads JSON-LD without sending anything and removes HTML and URL credentials", () => {
    document.body.innerHTML = '<h1>Short title</h1><script type="application/ld+json"></script>';
    document.querySelector("script")!.textContent = JSON.stringify({
      "@graph": [{ "@type": "JobPosting", title: "Senior Software Engineer", hiringOrganization: { name: "Example Health" }, description: `<p>${JD}</p><script>secret</script>` }],
    });
    const job = readJob(document, URL);
    expect(job.title).toBe("Senior Software Engineer");
    expect(job.company).toBe("Example Health");
    expect(job.description).toBe(JD.trim());
    expect(job.url).toBe("https://careers.example/jobs/123");
    expect(job.method).toBe("structured data");
  });

  it("reads Workday's advert before Apply, without reading entered form answers", () => {
    document.body.innerHTML = `<header>Account</header><h1>Rails developer</h1><div data-automation-id="jobPostingDescription"><h2>Responsibilities</h2><p>${JD}</p><form><textarea>Private answer</textarea><label>Secret field</label></form><input value="personal@example.com"></div>`;
    const job = readJob(document, URL);
    expect(job.description).toContain("Responsibilities");
    expect(job.description).toContain("Ruby on Rails");
    expect(job.description).not.toMatch(/Private|Secret|personal|Account/);
    expect(job.company).toBe(""); // Ask the User, never invent an employer from the hostname.
  });

  it("lets the User select any description, even shorter than structured text", () => {
    document.body.innerHTML = '<h1>A job</h1><main>Some different page text</main>';
    expect(readJob(document, URL, JD).description).toBe(JD.trim());
    expect(readJob(document, URL, JD).method).toBe("selected text");
  });

  it("does not take the first of multiple job adverts", () => {
    document.body.innerHTML = '<script type="application/ld+json"></script>';
    document.querySelector("script")!.textContent = JSON.stringify([1, 2].map((i) => ({ "@type": "JobPosting", title: `Job ${i}`, description: JD })));
    expect(() => readJob(document, URL)).toThrow("several jobs");
  });

  it("leaves an empty editor instead of scraping the body on an unsupported site", () => {
    document.body.innerHTML = '<h1>A job</h1><div>Account balance and private messages</div>';
    expect(readJob(document, URL).description).toBe("");
  });

  it("preserves job identity parameters but drops unrelated query data", () => {
    expect(pageUrl("https://example.com/careers?gh_jid=42&access_token=abc&email=x#apply")).toBe("https://example.com/careers?gh_jid=42");
    expect(() => pageUrl("file:///etc/passwd")).toThrow();
  });
});
