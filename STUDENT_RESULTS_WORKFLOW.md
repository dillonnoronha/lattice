# Lattice: student results → class dataset

Updated November 13, 2026.

## Instructions to give students

1. Open the class app and choose **Start a blank results sheet** in the sidebar.
   Do not use the sample investigation for your submission.
2. Under **Prepare data → Add an observation**, enter the instructor-provided section,
   semester, lab group code, experiment date, and trial number.
3. Enter the actual composition: element symbols and stoichiometric ratios. Fill optional
   A′/B′/B″ sites only when present. These are formula ratios, not weighed masses.
4. Select the observed phase and bubble response. **Maybe** means tested but ambiguous;
   **not tested** means the test was not performed. A compound that was **not made** should
   have a **not tested** bubble response. The app does not preselect successful outcomes.
5. Click **Build and check compound**, fix any issues, then **Add to project dataset**.
   Repeat for each independently performed experiment. Increment the trial number for repeats.
6. To correct an entry, choose it under **Recorded observation to edit**, click **Edit selected
   observation**, change the form, build/check, and **Save changes to observation**. This replaces
   the saved record while preserving its experiment ID. **Cancel edit and start a new observation**
   leaves the earlier experiment intact.
   Use **Delete observation** beside a recorded result, then **Confirm delete**, to remove
   just that experiment from the project dataset and submission CSV. A separately recorded
   notebook observation remains in the notebook and can be explicitly added again.
   **Start fresh → Clear recorded observations** removes all observations added through the
   entry form or notebook from the project dataset and submission CSV, and resets the entry form.
   Imported data and notebook entries are kept; notebook observations can be explicitly added again.
   Other projects, older saved revisions, and downloaded files are also kept.
   Choose **Keep my data** to cancel the reset.
7. Click **Download student submission CSV** below the form (also in **Share findings**).
   Submit that CSV to the course LMS assignment. It contains all your added observations,
   regardless of analysis filters; imported class/sample records and predictions are excluded.

Use a non-identifying lab group code assigned by the instructor, not student names or emails.
Do not place names/emails in notes. Keep experiment IDs unchanged when resubmitting corrections.
Use a new form entry for an actual new trial. The app generates the IDs automatically.

To continue another day, also download **Portable project · JSON** in Share findings and reopen
that bundle. JSON is your editable backup; the student CSV is the file to submit. Uploading a CSV
as an analysis project does not automatically turn imported records into your own submission.

Experiments planned in **Experiment Designer → Lab notebook** use the same submission workflow.
Record the measured outcomes, section, semester, group, date, and trial in the notebook. Save the
observation, resolve any validation issues, then **Add observed experiment to project data**.
It becomes part of the same student submission CSV. Later notebook edits do not change that
dataset snapshot; use **Recorded observation to edit** to correct the submitted record.

## Instructor collection

1. Provide students with a real hosted app URL, a consistent section/semester label, group codes,
   and an LMS submission assignment. The localhost preview is accessible only on its host computer.
2. Download the student CSV submissions from the LMS.
3. In the app, start a blank results sheet for a new class dataset, or open your current master file.
4. Choose **Prepare data → Combine submission CSVs** and upload the files together.
5. Leave **Include the whole current project dataset** checked only when appending to your master.
6. Review validation messages and conflicts. An unchanged experiment ID/content pair is counted once.
   Distinct experiment IDs survive even with identical chemistry/outcomes. Changed versions of the
   same ID stop intake for review: retain the correct submission file, then upload the batch again.
7. Download **combined class CSV** for the master record, or choose **Open combined class results
   as a new project** to inspect it immediately. Download a project bundle for backup as well.

**Submission coverage** shows received experiment counts and confirmed outcomes for each section,
semester, and lab group. It is available during intake and on Overview, with a downloadable summary.
Use the **LabGroup** sidebar filter to inspect a group's records. Compare coverage with your roster
to identify missing submissions; the app does not know the class roster.

This intake accepts the new student submission format without requiring access to contact data.
The separate legacy **Combine student files** tool remains instructor-gated. Old surveys still import
through **Import a spreadsheet or project** / **Import another semester**. Legacy records without
experiment IDs are retained rather than guessed to be duplicates; review overlaps manually.

## What is and is not connected

The app now supports validated entry, student CSV download, and batch class-file intake. It does
not send files to the LMS, collect files in a shared inbox, or automatically update a remote database.
The instructor reviews/imports the submitted files. A publicly reachable student deployment is a
separate step; the local development preview is not a class-wide link.

The recorded outcomes match the current class schema: categorical phase and bubbling. Quantitative
measurements such as gas volume, reaction time, or instrument readings need a course-defined schema
before they can be analyzed as structured variables; free-text notes are not a substitute.

## Reply for your work partner

“We now have a direct-entry workflow in the app. Students start a blank results sheet, enter and
validate each experiment, and download one student submission CSV for the LMS. We can upload those
CSVs together to create or extend the class dataset. Experiment IDs preserve repeat trials and flag
conflicting resubmissions. We still need to provide a hosted app link and the LMS collection assignment;
there is no automatic shared-database submission yet. The old survey remains a compatible fallback.”
