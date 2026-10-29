import type { ReactNode } from "react";
import { Link } from "react-router-dom";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="space-y-2 text-sm leading-6 text-slate-700 dark:text-slate-300">{children}</div>
    </section>
  );
}

/** Public privacy policy for the browser extension, linked from its store listing. Keep it
 * in step with the extension's permissions and ADR-0017. */
export function ExtensionPrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl space-y-8 px-4 py-10">
      <header className="space-y-2">
        <p className="font-mono text-xs font-bold tracking-[0.2em] text-pink-700 uppercase dark:text-pink-400">JobWeaver</p>
        <h1 className="text-2xl font-semibold">Browser extension privacy policy</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          The JobWeaver extension fills job application forms from your own JobWeaver documents. You review every value, and you
          submit the form yourself. It never submits a form.
        </p>
      </header>

      <Section title="What the extension can access">
        <p>
          Your JobWeaver account, after you click Connect and approve it on JobWeaver. A connection lasts a limited time, ends when
          the browser closes, and can be revoked at once in Settings.
        </p>
        <p>
          A careers page only when you act on it: clicking the extension in the toolbar gives it the tab you are on, and other
          sites, or forms embedded from another site, are used only after you allow that site. It does not read other tabs or
          your browsing history.
        </p>
      </Section>

      <Section title="What it sends to JobWeaver">
        <ul className="list-disc space-y-1 pl-5">
          <li>A job advert you chose to read and save: its title, company, address and the description you reviewed.</li>
          <li>The labels of a form&apos;s questions, when you ask for suggested answers. Not what you or the page typed into them.</li>
          <li>Answers you choose to save for reuse, and that you applied, when you confirm you submitted an application.</li>
        </ul>
        <p>
          Form values are filled in the page from your reviewed JobWeaver profile and documents. The extension does not send the
          contents of form fields, cookies or passwords anywhere.
        </p>
      </Section>

      <Section title="AI">
        <p>
          Suggested answers are written by JobWeaver&apos;s AI providers from your own Facts, only after you accepted the AI notice
          in JobWeaver. Questions about work authorisation, salary, notice period and similar are answered only from answers you
          saved yourself, and forms that ask for answers not written by AI get notes from your Facts instead.
        </p>
      </Section>

      <Section title="What it keeps in your browser">
        <p>
          The connection and any unfinished review are kept in the browser&apos;s session storage, private to the extension, and
          cleared when the browser closes. Unfinished review expires after 30 minutes. With your permission it can save your PDFs
          to your Downloads folder.
        </p>
      </Section>

      <Section title="What it never does">
        <ul className="list-disc space-y-1 pl-5">
          <li>Submit a form, or send anything to an employer.</li>
          <li>Sell or share your data, show ads, or use analytics or tracking.</li>
          <li>Use your data for anything except filling your applications.</li>
        </ul>
        <p>
          The use of information received through the extension adheres to the Chrome Web Store User Data Policy, including the
          Limited Use requirements.
        </p>
      </Section>

      <Section title="Removing your data">
        <p>
          Revoke the connection in JobWeaver under Settings, Browser extension, or remove the extension from your browser. Deleting
          your JobWeaver account deletes everything the extension saved to it.
        </p>
      </Section>

      <p className="text-sm">
        <Link to="/" className="underline">
          Go to JobWeaver
        </Link>
      </p>
    </main>
  );
}
