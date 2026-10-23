# Task Sniffer — Minimal Multi-User Extension

## Objective

Extend the existing Task Sniffer application to support multiple users with personalized job profiles and preferences across the current web frontend and Telegram bot.

**This is an incremental enhancement, NOT a redesign, rewrite, or architectural overhaul.**

Repository: `/home/retro/Projects/web/Task_Sniffer`

## 1. Audit before changing anything

Inspect the existing repository and identify:

- Current frontend structure, layout, routes, and components.
- Existing backend models, APIs, authentication, and matching services.
- Existing Telegram commands, handlers, and user identity mapping.
- Existing job database, ingestion pipeline, and scheduler.
- Which profile, preference, and personalization features already exist.
- Any confirmed defects that directly prevent multi-user support.

Do not edit files during this initial audit.

Return a concise report distinguishing existing functionality, missing functionality, and actual defects. Do not propose replacing components or services that already work.

## 2. Preserve the existing application

These constraints are mandatory:

- Do not redesign the frontend.
- Do not change the existing visual style, layout, navigation, or branding unless a specific change is essential to the requested functionality.
- Do not replace the Telegram bot's existing interaction model.
- Do not rename routes, commands, models, or API endpoints without a demonstrated necessity.
- Do not replace working services with new implementations.
- Do not rewrite the application or introduce unnecessary dependencies.
- Do not modify unrelated features.
- Do not add subscription payments, LLM integration, a Telegram Mini App, or unrelated enhancements.
- Preserve existing job records, users, application records, and other data.

## 3. Add only the missing multi-user functionality

Extend the existing user and preference models, reusing current structures wherever possible.

Support these preferences where not already implemented:

- Skills and skill aliases.
- Preferred job titles.
- Experience level.
- Location.
- Remote, hybrid, or onsite preference.
- Employment types.
- Optional salary expectations and exclusions.

Use the existing database and migration conventions. Make changes backward-compatible and preserve existing data.

Do not create duplicate models or tables when an existing model can be extended appropriately.

## 4. Personalize job matching

Reuse the existing job retrieval and matching pipeline.

For each user:

- Retrieve jobs using their preferences.
- Rank jobs using the existing matching logic, extending it only where necessary.
- Explain match results using actual matching signals.
- Respect hard eligibility constraints and explicit exclusions.
- Allow incomplete profiles to continue using existing job-search functionality.

Keep the ingestion pipeline and canonical job database shared across users. Do not run a separate scraper for each user.

Do not introduce an LLM or replace the matching algorithm as part of this task.

## 5. Extend the existing Telegram bot

Keep all working commands and flows.

Add only the missing functionality needed for users to:

- View and edit their profiles.
- Configure job preferences.
- Retrieve personalized jobs.
- Save jobs if supported by the existing application.
- Configure or pause notifications if supported.

Reuse existing handlers and backend services where possible. Add inline buttons only where they materially improve the existing experience.

Ensure Telegram platform IDs are mapped correctly to internal database users. Never assume the two identifiers are interchangeable.

Ensure preferences and saved jobs are isolated per user.

## 6. Extend the existing frontend

Preserve existing pages, styling, components, and navigation.

Add or minimally extend the relevant existing page or component to allow users to view and edit their job preferences.

Connect existing job listings to personalized matching results using the established API client and authentication flow.

Do not introduce mock data, placeholder authentication, or duplicate business logic.

## 7. Security and regression tests

Verify:

- Users can access and update only their own preferences.
- Existing users and jobs remain intact.
- Telegram identity mapping is correct.
- Job matching respects each user's preferences.
- Existing commands, routes, and features continue working.
- Existing authentication and URL-validation safeguards are not weakened.

Add focused tests for new behavior and run relevant existing tests.

Do not claim tests pass unless they were actually executed.

## 8. Implementation process

Proceed in small, reviewable steps:

1. Complete the read-only audit and report findings.
2. Identify the minimum required changes.
3. Implement the smallest safe backend and database changes.
4. Test the new profile and matching behavior.
5. Extend Telegram with the required functionality.
6. Extend the frontend with the required functionality.
7. Run regression tests and summarize the results.

After the audit, proceed with low-risk, backward-compatible work. Stop and request approval before destructive migrations, production data changes, or changes that could invalidate existing integrations.

## Final requirement

The result must look and behave like the existing Task Sniffer application, with the necessary multi-user functionality added.

Prefer extending existing code over creating new code. If a requested feature already works, leave it alone.

At completion, report exactly what changed, which files were affected, which tests ran, and what remains incomplete.

# Task Sniffer — Minimal Telegram Bot UI Enhancement

## Objective

Extend the existing Task Sniffer Telegram bot with an intuitive, button-driven interface while preserving all working commands, handlers, backend services, database models, and job-ingestion functionality.

Repository: `/home/retro/Projects/web/Task_Sniffer`

**This is a targeted enhancement, not a redesign or rewrite.**

The primary goal is to let users navigate the existing bot using Telegram inline keyboards while retaining slash commands as shortcuts.

## 1. Audit the existing bot first

Before editing any files, inspect:

- Telegram framework and version.
- Bot entry point and registration of commands and handlers.
- Existing commands, conversation flows, and callback handling.
- Current job-search and matching services.
- User, profile, and preference models.
- Telegram-to-internal-user identity mapping.
- Existing saved-job, application-tracking, and notification functionality.
- Tests, environment variables, and deployment configuration.

Identify which features already work and which are missing.

Do not replace existing handlers or services simply to introduce buttons. Reuse the current architecture wherever possible.

After the audit, implement the minimal changes needed for the UI.

## 2. Add an inline-keyboard main menu

When a user starts the bot with `/start`, show a welcome message and a main menu.

Use Telegram inline keyboards with these options, adapting the menu to the features actually implemented:

- 🔎 Find Jobs
- 👤 My Profile
- ⚙️ Job Preferences
- ⭐ Saved Jobs
- 📋 My Applications
- 🔔 Job Alerts
- ❓ Help

Do not display nonfunctional buttons. If a feature does not exist, either omit it or clearly indicate that it is not yet available.

Keep the existing bot personality, message conventions, and working commands unless a change is necessary.

## 3. Implement navigation

Use callback handlers for inline-keyboard interactions.

Provide consistent navigation where appropriate:

- Back
- Main Menu
- Cancel
- Previous Page
- Next Page

Prefer editing the existing Telegram message when practical rather than sending a new message for every button press.

Handle expired callback queries, stale buttons, unexpected callback data, repeated clicks, and API failures gracefully.

A button must perform its advertised action. Do not implement buttons that merely display a success message without completing the underlying operation.

## 4. Job discovery UI

The Find Jobs option should invoke the existing job retrieval and matching services.

Present jobs in a concise format containing available information:

- Job title and employer.
- Location and work arrangement.
- Employment type and salary, when available.
- Publication date or freshness information.
- Match score or category, if calculated.
- A brief explanation of the matching signals.
- A risk warning when relevant.

Provide contextual buttons where supported:

- Open Job
- Apply on Original Site
- Save Job
- Track Application
- Next / Previous

Requirements:

- Reuse existing job-detail and application URLs.
- Do not invent or reconstruct application URLs.
- Do not present unvalidated links as trusted destinations.
- Keep suspicious or unresolved URLs visibly flagged.
- Do not invent match scores or verification claims.
- Handle jobs with missing fields without crashing.
- Support pagination without repeatedly showing the same jobs.

Do not duplicate the matching algorithm inside Telegram handlers.

## 5. Profile and preferences UI

The profile menu should let users view and update their existing profile fields.

Where supported by the backend, allow users to manage:

- Skills.
- Preferred job titles.
- Experience level.
- Location.
- Remote, hybrid, or onsite preference.
- Employment types.
- Optional salary expectations.
- Excluded keywords or job titles.

Use short conversational steps and buttons for common selections. Accept text input for skills, titles, and other free-form values.

Allow users to cancel an edit, go back where appropriate, and return to the main menu.

Validate input before saving. Confirm success only after the backend has successfully persisted the change.

Do not require users to complete every optional field before searching for jobs.

If multi-user preferences are not yet implemented, identify the minimum backend changes required and reuse existing models and services. Do not create a separate Telegram-only profile system.

## 6. Preserve slash commands

Retain all existing working commands.

Add or improve commands only where needed, for example:

- `/start` — welcome and main menu.
- `/help` — usage instructions.
- `/jobs` — search for jobs.
- `/profile` — view profile.
- `/settings` — manage preferences.
- `/saved` — view saved jobs.
- `/alerts` — manage notifications.

These commands and their corresponding buttons must invoke the same underlying services. Avoid duplicating business logic between command handlers and callback handlers.

Do not remove or rename existing commands without a demonstrated need.

## 7. User identity and data isolation

Every action must operate on the correct internal user.

- Resolve Telegram users through the existing identity mapping or implement a minimal, explicit mapping if necessary.
- Never treat a Telegram platform user ID as an internal database primary key without an established mapping.
- Never allow one user to view or modify another user's profile, preferences, saved jobs, or applications.
- Enforce authorization in the backend.
- Handle unknown or unlinked users safely.
- Do not log bot tokens or sensitive user data.

Do not introduce account linking or authentication redesign unless required for the requested functionality.

## 8. Notifications and alerts

If job alerts already exist, add simple buttons to view or change their existing settings.

Where supported, allow users to:

- View their alert status.
- Pause notifications.
- Resume notifications.
- Configure available notification preferences.

Preserve the existing scheduler and delivery architecture.

Do not create a new scheduler if one already exists. Do not introduce duplicate notifications, change notification frequency unexpectedly, or enable mass notifications as part of this UI task.

If persistent notification deduplication is missing, report it and propose the smallest safe fix.

## 9. User experience requirements

- Use clear, concise Telegram messages.
- Keep button labels short and unambiguous.
- Use consistent navigation across menus.
- Prevent invalid callback data from causing crashes.
- Handle empty results and incomplete profiles helpfully.
- Provide meaningful error messages and recovery paths.
- Respect Telegram message-size and rate limits.
- Avoid unnecessary message spam.
- Keep the bot usable on mobile screens.
- Do not introduce a Telegram Mini App, web-based dashboard, or unrelated UI framework.

## 10. Testing

Add or update focused tests for:

- Main-menu rendering.
- Callback routing and navigation.
- Existing commands remaining functional.
- Job retrieval and pagination.
- Profile and preference editing.
- Correct user identity mapping.
- User-data isolation.
- Saving jobs and tracking applications, where implemented.
- Invalid callback data and backend failures.
- Notification pause/resume behavior, where implemented.

Mock Telegram API calls during tests. Do not send real notifications to users.

Run the existing relevant tests and report their actual results.

## 11. Implementation constraints

- Do not redesign the web frontend.
- Do not rewrite the backend.
- Do not replace working bot handlers without necessity.
- Do not modify the ingestion pipeline unless a confirmed dependency requires it.
- Do not add LLM integration, subscriptions, payment processing, or new external services.
- Do not introduce unnecessary dependencies.
- Do not perform destructive database migrations or production data changes without approval.
- Preserve existing behavior unless a specific change is required.
- Follow existing code style, framework conventions, and deployment practices.

## 12. Final report

Summarize:

1. Existing Telegram functionality discovered.
2. UI enhancements implemented.
3. Files modified.
4. Existing commands preserved.
5. New buttons and their actual behavior.
6. Tests executed and results.
7. Any backend work required but not completed.
8. Any remaining limitations or deployment steps.

## Success criterion

A user can open Task Sniffer in Telegram, navigate its existing functionality through clear inline buttons, search and interact with jobs, manage supported profile preferences, and return to the main menu without losing existing functionality.

**Start with the audit, then implement the smallest safe change set. Preserve what works. Extend only what is necessary.**