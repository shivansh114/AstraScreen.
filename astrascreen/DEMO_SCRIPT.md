# 5-minute demo script (what to click, what to say)

**Before:** run `python run.py`, sign in as *Reliability / QA engineer*. Keep the PPT slide 3 in mind.

1. **Problem (20 s)** – "Burn-in takes 168 hours. A fixed limit only catches a part once it crosses 50 µA.
   AstraScreen reviews every part after 24 hours."
2. **Load sample lot L07 (20 s)** – point at the four steps: validate, Module A, Module B, Module C.
3. **Module A (40 s)** – click `L07-B1-S14`: "44.8 µA passes the 50 µA limit, but it is 4x the lot median.
   The peer chart shows it far from its batch-mates."
4. **Module B (40 s)** – click `L07-B1-S31`: "Only 27 µA at 24h – a fixed limit passes it. Our forecast says
   about 51 µA at 168h." Record **Investigate** with a note.
5. **Module C, our unique idea (60 s)** – point at Board 3: "Six flags bunched in one corner. That is a socket or
   hot-zone fault, not six bad parts. The forecast is paused and the parts are retested instead of rejected."
   Click one teal socket and record **Retest in another board**.
6. **Reveal real 168h (40 s)** – click **Reveal real 168h readings**: "The two parts we flagged at 27 µA really went
   over the limit at 168h – caught 144 hours early. The fixed limit caught none of them at 24h.
   Average forecast error 0.39 µA." (Say clearly: simulated lot.)
7. **Trust and records (30 s)** – open **QA report** and **Audit log**: every decision, who made it, when, which model.
8. **Close (10 s)** – "Runs offline on one lab workstation. Works alongside existing delta and PDA checks."

**Likely questions**
- *Is this real ISRO data?* No – simulated lots with injected faults. Next step: replay historical ISRO lots.
- *What if board/slot IDs are missing?* Modules A and B still work; Module C needs position fields.
- *Can it reject parts by itself?* No. It advises; QA decides; hard limits still apply.
