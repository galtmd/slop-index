@echo off
REM Round 2: social epidemiologists and sociologists of health, plus two controls.
REM Fetches PubMed records; citation counts are added separately if iCite is unreachable from this machine.
cd /d "%~dp0"
python -m slop_index run --slug krieger-n     --author "Krieger, Nancy" --surname Krieger
python -m slop_index run --slug hardeman-rr   --author "Hardeman, Rachel R" --author-variant "Hardeman, Rachel" --surname Hardeman
python -m slop_index run --slug jones-cp      --author "Jones, Camara Phyllis" --author-variant "Jones, Camara P" --author-variant "Jones, Camara" --surname Jones
python -m slop_index run --slug geronimus-at  --author "Geronimus, Arline T" --author-variant "Geronimus, Arline" --surname Geronimus
python -m slop_index run --slug bowleg-l      --author "Bowleg, Lisa" --surname Bowleg
python -m slop_index run --slug ford-cl       --author "Ford, Chandra L" --author-variant "Ford, Chandra" --surname Ford
python -m slop_index run --slug metzl-jm      --author "Metzl, Jonathan M" --author-variant "Metzl, Jonathan" --surname Metzl
python -m slop_index run --slug case-a        --query "\"Case, Anne\"[Full Author Name] AND (Deaton[Author] OR Princeton[Affiliation])" --surname Case
echo.
echo Done. If the iCite step failed, that is expected on this machine; the citation counts get added separately.
pause
