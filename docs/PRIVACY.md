# Privacy design note

SkillWatch AI exists to answer one question: *roughly how many people are in this training room, and is the sanctioned
equipment there?* It is built so that it cannot answer any other question about a person.

## What the system does and does not identify

| | Identified or stored? |
|---|---|
| **How many people** are in a frame (an aggregate number) | **Yes.** This is the only thing computed about people. |
| **Who** a person is (name, ID, face match) | **No.** There is no face recognition, face embedding, face database or identity lookup anywhere in the code. |
| **Tracking** a person across frames or days | **No.** Counts are made per frame and combined by a median. No person is followed, assigned an id, or matched between frames. |
| Age, gender, emotion, clothing, gait, any attribute of a person | **No.** Not computed. |
| **Raw video** | **Not stored by the dashboard, and never uploaded in low-bandwidth mode.** The demo clips are synthetic. |
| **Raw frames** | **Not written to disk.** Frames exist only in memory while a clip is analysed. |
| **Thumbnails** | **Yes, one per observation**, with every detected person region pixelated *before* the image is drawn on or saved. |
| Attendance claimed by the centre | **Yes**, as a number per batch per day. No names. |
| Staff accounts (name, email, hashed password, role) | **Yes.** Needed to sign in. Passwords are bcrypt-hashed. |

## How the guarantees are enforced in code

- **Counting only.** `vision/person_counter.py` returns boxes and a count. Nothing in the repository imports a face detector or recogniser.
- **No raw frame persistence.** The sampler yields frames in memory. The only image the pipeline writes is the pixelated thumbnail, and the edge agent writes it to a temporary folder, reads it into its queue, and deletes it.
- **Small images.** Thumbnails are downscaled (224-320 px wide) so fine detail is not present to begin with.
- **Aggregate storage.** The database holds counts, equipment totals, scores and a path to the thumbnail. There is no table that could hold a person.

## Limits you should know about

1. **Pixelation is performed by the same code that detects people.** If the detector misses a person, that person is *not* pixelated in the thumbnail. A thumbnail may therefore show a person the detector failed to find. At 224-320 px wide faces are generally not identifiable, but this is a risk to reduce, not a guarantee.
2. **Even aggregate monitoring is surveillance.** A camera in a room records people whether or not software identifies them. Deployment needs a lawful basis, notice to trainees and staff (signs and written notice), a defined retention period, and a clear owner. This note describes what the software does; it is not legal advice and it does not replace a data protection assessment under the applicable law.
3. **Retention is not automatic yet.** Observations and thumbnails are kept until deleted. A production deployment should delete thumbnails after a fixed period (for example 30 days) and keep only the numbers.
4. **The camera itself is outside this software.** If the centre's CCTV recorder keeps video, that is governed by the centre, not by SkillWatch AI.
5. **Staff data.** Alert comments are written by officers and could contain personal information typed by a human. Train officers to keep comments factual and free of names of trainees.
6. **Demo data is synthetic.** No real person appears in the demo footage, evaluation set or thumbnails in this repository.
