Summary
=======
A program that can convert LendingClub monthly statements to QIF files for easy importing into Quicken or GnuCash.

Usage
=====
To see what the QIF file will look like for a statemnt run:

    python parse.py ~/Downloads/Monthly_Statement_2014_03.pdf

To convert a years worth of statements into QIFs, you can use the following
   
   for file in `ls ~/Downloads/Monthly_Statement_2013_*.pdf`; do python parse.py $file > ${file}.qif; done

Dependencies
============
The program assumes that pdfminer-20140328 and fuzzyparsers-0.9.0 modules are available for import