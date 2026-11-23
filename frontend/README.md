# AVG Frontend (Next.js)

Next.js (App Router) + TypeScript + Tailwind + Monaco Editor, as in the architecture report.

    npm install                              # downloads the libraries listed in package.json
    cp .env.local.example .env.local         # copies the settings file (set NEXT_PUBLIC_MOCK)
    npm run dev                              # starts the dev server at http://localhost:3000

Mock mode: log in with any email and an 8+ character password. Emails starting with "ta" log in as a TA.
