from __future__ import print_function
from pdfminer.layout import LAParams
from pdfminer.pdfparser import PDFParser
from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice
from fuzzyparsers import parse_date
from itertools import islice
import re
import decimal
import sys

splits = {
    "Funds Lent" : {
        "section": "CASH DETAILS",
        "category": "Investments:LendingClub:Outstanding Principal"
    },
    "Principal Received" : {
        "section": "CASH DETAILS",
        "category": "Investments:LendingClub:Outstanding Principal"
    },
    "Loan Interest" : {
        "section": "CASH DETAILS",
        "category": "Income:Interest:LendingClub"
    },
    # Starting in Aug 2014, the entry 'Loan Interest' was renamed
    # to 'Interest Received'.  To handle both types of PDFs, search for
    # either string
    "Interest Received" : {
        "section": "CASH DETAILS",
        "category": "Income:Interest:LendingClub"
    },
    "Service Fees" : {
        "section": "CASH DETAILS",
        "category": "Expenses:Service Fee:LendingClub"
    },
    "Adjustments/Credits" : {
        "section": "CASH DETAILS",
        "category": "Income:LendingClub:Adjustments"
    },
    "Collection Fees" : {
        "section": "CASH DETAILS",
        "category": "Expenses:Bank Charges:Collection Fees:LendingClub"
    },
    "Recovery Fees" : {
        "section": "CASH DETAILS",
        "category": "Expenses:Bank Charges:Recovery Fees:LendingClub"
    },
    "Recoveries" : {
        "section": "CASH DETAILS",
        "category": "Income:LendingClub:Recoveries"
    },
    "Late Fees Received" : {
        "section": "CASH DETAILS",
        "category": "Income:LendingClub:Late Fees"
    },
    "Losses (charged off loans)" : {
        "section": "EARNINGS SUMMARY",
        "category": "Expenses:Bank Charges:Loan Charged Off:LendingClub",
        "sourceCategory": "Investments:LendingClub:Outstanding Principal",
    }
}

def readPdf(file):
    # Open a PDF file.
    fp = open(file, 'rb')

    # Create a PDF parser object associated with the file object.
    parser = PDFParser(fp)
    
    # Create a PDF document object that stores the document structure.
    # Supply the password for initialization.
    document = PDFDocument(parser)
    
    # Check if the document allows text extraction. If not, abort.
    if not document.is_extractable:
        raise PDFTextExtractionNotAllowed

    # Create a PDF resource manager object that stores shared resources.
    rsrcmgr = PDFResourceManager()
        
    # Set parameters for analysis.
    laparams = LAParams(line_margin=0.1)
    
    pages = []

    # Create a PDF page aggregator object.
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    for page in islice(PDFPage.create_pages(document), 2):
        interpreter.process_page(page)
        # receive the LTPage object for the page.
        layout = device.get_result()
        pages.append(layout)
        
    return pages
    
def findTextElement(obj, text):
    for child in obj:
        try:
            childText = child.get_text().strip()
            if child.get_text().strip() == text:
                return child
        except AttributeError:
            # No problem, the object must not be something with text
            continue
            
        if hasattr(text, "match") and callable(getattr(text, "match")) and text.match(childText):
            return child

        if childText == text:
            return child

    
def findPageWithSection(pages, sectionTitle):
    for page in pages:
        if findTextElement(page, sectionTitle) is not None:
            return page

def dumpPage(page):
    for child in page:
        print(child)

def elementRightOf(parent, obj, elementFilter=None):
    rightOf = [x for x in parent
               if obj.is_voverlap(x) and obj.hdistance(x) > 0]
    
    if elementFilter:
        rightOf = [x for x in rightOf if elementFilter(x)]
    return min(rightOf, key=lambda child: obj.hdistance(child))
    
def hasGetText(obj):
    return hasattr(obj, 'get_text') and callable(obj.get_text)

def textRightOf(parent, obj):
   return elementRightOf(parent, obj, elementFilter=hasGetText) 
   
class MissingTextElementException(Exception):
    pass

def amountRightOf(obj, text):
    textElement = findTextElement(obj, text)
    if not textElement:
        raise MissingTextElementException("The text '%s' was not found" % text)
        
    rightOf = textRightOf(obj, textElement)
    textAmount = rightOf.get_text().strip()
    
    sign = 1
    negativeMatch = re.match("^\((.*)\)$", textAmount)
    if negativeMatch:
        textAmount = negativeMatch.group(1)
        sign = -1
    
    dollarMatch = re.match("^\$(.*)$", textAmount)
    if dollarMatch:
        textAmount = dollarMatch.group(1)
        
    # Strip commas from large amounts
    textAmount = textAmount.replace(',','')
    
    if textAmount == "-":
        amount = decimal.Decimal("0.0")
    else:
        amount = decimal.Decimal(textAmount) * sign
    return amount

class DateNotFoundException(Exception):
    pass

def findStatementDate_pre201504(obj):
    dateRegex = re.compile("(\w+)\s+[0-9][0-9]-([0-9][0-9])\.\s+([0-9][0-9][0-9][0-9])")
    dates = findTextElement(obj, dateRegex)
    if not dates:
      raise DateNotFoundException("Old style date not found in page")
    dateMatch = dateRegex.match(dates.get_text().strip())
    return parse_date("%s %s %s" % ( dateMatch.group(1), dateMatch.group(2), dateMatch.group(3)))

def findStatementDate_after201504(obj):
    dateRegex = re.compile("\w+\s+[0-9][0-9]\s+[0-9][0-9][0-9][0-9]\s+-\s+(\w+)\s+([0-9][0-9])\s+([0-9][0-9][0-9][0-9])")
    dates = findTextElement(obj, dateRegex)
    if not dates:
      raise DateNotFoundException("New style datNew style date not found in page")
    dateMatch = dateRegex.match(dates.get_text().strip())
    return parse_date("%s %s %s" % ( dateMatch.group(1), dateMatch.group(2), dateMatch.group(3)))

def findStatementDate(obj):
    try:
        return findStatementDate_pre201504(obj)
    except DateNotFoundException:
        return findStatementDate_after201504(obj)

def calculateSplitAmounts(obj):
    newSplits = splits.copy()
    for split in splits:
        pageWithSection = findPageWithSection(obj, splits[split]['section'])
        try:
            amount = amountRightOf(pageWithSection, split)
            newSplits[split] = splits[split].copy()
            newSplits[split]['amount'] = amount
            if newSplits[split]['amount']:
                if 'sourceCategory' in splits[split]:
                    newSplits[split + " source"] = {
                        'category': splits[split]['sourceCategory'],
                        'amount': newSplits[split]['amount'] * -1
                    }
        except MissingTextElementException:
            print("Split %s was not found, so it will be ignored" % split, file=sys.stderr)
    
    return newSplits
    
def totalSplits(splits):
    total = decimal.Decimal(0)
    for split in splits:
        if 'amount' in splits[split]:
            total += splits[split]['amount']
    return total
        

pdf = readPdf(sys.argv[1])
splits = calculateSplitAmounts(pdf)
total = totalSplits(splits)

print("!Type:Bank")
date = findStatementDate(findPageWithSection(pdf, "CASH DETAILS"))
print("D%s" % date.strftime("%m/%d/%Y"))
print("T%s" % total)
for split in splits:
    if 'amount' in splits[split]:
        splitAmount = splits[split]['amount']
        category = splits[split]['category']
        print("S%s" % category)
        print("E%s" % split)
        print("$%s" % splitAmount)
        
print("^")
