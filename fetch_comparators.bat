@echo off
REM Fetches PubMed records and iCite citations for the calibration roster,
REM then scores everyone. Run from the slop-index folder. Needs Python 3.9+.
cd /d "%~dp0"
python -m slop_index run --slug mega-jl       --author "Mega, Jessica L" --author-variant "Mega, Jessica" --surname Mega
python -m slop_index run --slug kariko-k      --author "Kariko, Katalin" --author-variant "Karikó, Katalin" --surname Kariko
python -m slop_index run --slug charpentier-e --author "Charpentier, Emmanuelle" --surname Charpentier
python -m slop_index run --slug bhattacharya-j --author "Bhattacharya, Jay" --surname Bhattacharya
python -m slop_index run --slug gupta-s       --author "Gupta, Sunetra" --surname Gupta
python -m slop_index run --slug kulldorff-m   --author "Kulldorff, Martin" --surname Kulldorff
python -m slop_index run --slug makary-ma     --author "Makary, Martin A" --author-variant "Makary, Martin" --surname Makary
python -m slop_index run --slug oz-mc         --author "Oz, Mehmet C" --surname Oz
python -m slop_index run --slug el-sayed-am   --surname El-Sayed
echo.
echo Done. Results are in the results folder; cached data is in the data folder.
pause
