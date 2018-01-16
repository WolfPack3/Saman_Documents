"""
unavista_mifid2_xml2csv.py

This script reads data from a UnaVista MIFID 2 XML text file, validated by an XSD file comprising
an ISO-20022 schema, and outputs selected data to a CSV file for ingestion into in-house MiFID 2
processing.

The character encodings for the output CSV file is assumed to be UTF-8.

Command line usage is as follows:

    python unavista_mifid2_xml2csv.py -in-xml {in_XML_path} -out-csv {out_CSV_path} [ optional arguments ... ]

with:

    * {in_path}     Path of input XML text file, which must exist and be readable

    * {out_path}    Path of output CSV text file, in directory with write access

and optional keyword arguments, in mutually exclusive groups, as follows:

    * -warn         Display warnings (default)
    * -no-warn      Supress warnings

Any command line argument containing spaces, hyphens, or commas (and, depending on the OS,
other reserved characters) must be quoted. If in doubt, quote the argument!

"""

import codecs
import argparse
import csv
import re
import os
import xml.etree.ElementTree as ElemTree
import datetime
import time


parser = argparse.ArgumentParser(description="UnaVista MIFID 2 XML to CSV column converter")
parser.add_argument('-in-xml', help='pathname of input XML text file or folder')
parser.add_argument('-out-csv', help='pathname of output CSV text file')
parser.add_argument('-clnt-mode', help='pathname of input config file')

parser_warn = parser.add_mutually_exclusive_group(required=False)
parser_warn.add_argument('-warn', dest='warn', help='Display warnings (default)', action='store_true')
parser_warn.add_argument('-no-warn', dest='warn', help='Suppress warnings', action='store_false')
parser.set_defaults(warn=True)

args = parser.parse_args()

'''
Background Info
===============

UnaVista Ltd is a company owned by the London Stock Exchange group, and UnaVista is a (hosted) software app.
They are very similar to Abide Financial / NEX Regulatory Reporting, and are in fact a competitor.

We don’t have the UnaVista specifications (and can’t have them in the absence of a partnership / NDA) but we
have some idea of their XSD/XML specification from:

  I spoke to Paul Kettle at LGT Vestra, and he said that they can’t share the UnaVista XML specification with
  us (either the XSD or documentation), which is fair enough, but did say he believes it is the ISO 20022
  standard with a header and footer.

and also sample messages.

The reason the SAXO XSD/XML looks similar is because it is a hybrid of the ISO 20022 XSD and the CSV format,
which I designed to simplify the mapping to CSV (more-or-less a one-to-one mapping at the field level) whilst
still including as much as possible of the XSD validation.

This approach was taken when Traiana were still implementing the mappings (slowly) but in hindsight (now the
mappings are being implemented faster, by you!) it would have made sense to ask SAXO to use the ISO 20022
standard … then this latest requirement would have already been done.


CSV columns
===========

  Currently only ISO XML maps are supported.


  Report Details  ( /Document/NRRMiFIRTxRpt/Tx[i] )
  --------------

   1  ReportStatus

       Indicates whether record is for a new transaction ('NEWT') or a cancellation 'CANC'

       Mandatory    :  New: Y   Cancel: Y

       Validation   :  'NEWT' or 'CANC'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New
                       /Document/NRRMiFIRTxRpt/Tx[i]/Cxl

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New
                       /Document/FinInstrmRptgTxRpt/Tx[i]/Cxl

       NOTES: When the notional amount changes, a new transaction report should be submitted


   2  TransactionReferenceNumber

       Transaction reference numbers (TRNs) should be unique to the executing Investment Firm for each transaction
       report. In cases where one or more ARMs are involved, the transaction reference number should always be
       generated at the executing Investment Firm level. The TRN should not be re-used, except where the original
       transaction report is being corrected or cancelled in which case the same transaction reference number
       should be used for the replacement report as for the original report that it is being replaced.

       Mandatory    :  New: Yes   Cancel: Yes

       Validation   :  Up to 52 uppercase alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxId
                       /Document/NRRMiFIRTxRpt/Tx[i]/Cxl/TxId

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/TxId
                       /Document/FinInstrmRptgTxRpt/Tx[i]/Cxl/TxId

       NOTES :  If the report is a cancellation report, a transaction with the same transaction reference number
                should have been reported by the executing entity before.

                If the report is a cancellation report, this transaction should not have been cancelled before.


   3  TradingVenueTransactionIdentificationCode

       This is a number generated by trading venues and disseminated to both the buying and the selling parties in
       accordance with Article 12 of [RTS 24 on the maintenance of relevant data relating to orders in financial
       instruments under Article 25 of Regulation 600/2014 EU].

       This field is required only for the market side of a transaction executed on a trading venue.

       Must be blank if Venue (45) equals either 'XOFF' or 'XXXX'

       Mandatory    :  New: Conditional   Cancel: Blank

       Validation   :  Up to 52 uppercase alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdgVnTxId

       ISO XML map  :  [TODO]


   4  ExecutingEntityIdentificationCode

       Code identifying the entity executing the transaction

       Mandatory    :  New: Yes   Cancel: Yes

       Validation   :  Valid LEI code (as described in ISO 17442), comprising 20 alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/ExctgrPty
                       /Document/NRRMiFIRTxRpt/Tx[i]/Cxl/ExctgrPty

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/ExctgPty
                       /Document/FinInstrmRptgTxRpt/Tx[i]/Cxl/ExctgPty


   5  InvestmentFirmCoveredBy201465EU

       Indicates whether the entity identified by ExecutingEntityIdentificationCode (4) is an investment firm covered
       by Directive 2014/65/EU

       Mandatory    :  New: Yes   Cancel: Blank

       Validation   :  'true' or 'false'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InvstmtPrtyInd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx/New/InvstmtPtyInd



  Buyer Identification & Additional Details
  -----------------------------------------

  (For fields 6 to 12, iterate over /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j] )

   6  (7.1)  BuyerIdentificationCodeType                                                                 (REPEATABLE)

       Used to identify the correct type for Buyer identification code BuyerNPCode (7)

       Mandatory    :  New: Y   Cancel: Blank

       Validation   :  pipe ('|') delimited list of values each one of 'LEI', 'MIC', 'INTC', 'NIND', 'CCPT', 'CONCAT'

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/CdTp <> 'NIDN' then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/CdTp
                       Else:
                           'NIND'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/AcctOwnr/Id

       NOTES :         'NIND' - National Identifier
                       'CCPT' - Passport Number
                       'CONCAT' - Concatenation of Nationality, Date of Birth and Name abbreviation


   7  (7.2)  BuyerNPCode                                                                                 (REPEATABLE)

       Used to look up the associated buyer identifier held within the ISCI service and populate CSV fields 8 to 12

       Mandatory    :  New: N   Cancel: Blank

       Validation   :  pipe ('|') delimited list

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/ShrtCd

       ISO XML map  :  n/a

       NOTES        :  If a code is provided then it will be used to lookup against the ISCI service and enrich
                       the buyer fields as refernced within the ISCI specification document


   8  (7)  BuyerIdentificationCode                                                                     (REPEATABLE)

       Identification of entity who is purchasing the instruments

       The following entities should be reported with an LEI;

         * A central counterparty
         * A firm or an investment firm that is a market counterparty
         * An investment firm acting as a systematic internaliser
         * A client that is eligible for a LEI (see ESMA Guidance)

       Where a client is a natural persons, they should be identified according to RTS 22 Annex 2 - dependant on
       the country of nationality for that persons. For examples of how this field should be populated for different
       counterparties please see 5.8 of the ESMA guidance.

       Where an investment firm groups client orders, value 'INTC' should be reported here or in "Seller ID Code" (12).
       This allows the executing firm to be able to show records being bought on the market and sold to the client in
       different blocks. The executing investment firm must ensure the movement in and out of the 'INTC' book balances.
       See the ESMA guidance on grouping orders for more details.

       DEA clients should identify the DEA provider as the buyer or seller.

       Where the transaction was executed on a trading venue or on an organised trading platform outside of the
       Union that utilises a central counterparty (CCP) and where the identity of the acquirer is not disclosed,
       the LEI code of the CCP shall be used. Where the transaction was executed on a trading venue or on an
       organised trading platform outside of the Union that does not utilise a CCP and where the identity of
       the acquirer is not disclosed, the MIC code of the trading venue or of the organised trading platform
       outside of the Union shall be used.

       Where the acquirer is an investment firm acting as a systematic internaliser (SI), the LEI code of the
       SI must be used.

       Mandatory    :  New: Y if BuyerIdentificationCodeType (8) is set    Cancel: Blank

       Validation   :  pipe ('|') delimited list of value(s) which must each match one of the following:

         * If BuyerIdentificationCodeType (6) equals 'LEI' then value must comprise a valid LEI code
               as described in ISO 17442 comprising 20 alphanumeric characters

         * If BuyerIdentificationCodeType (6) equals 'MIC' then value must comprise a valid MIC code
               as described in ISO 10383 comprising 4 uppercase alphanumeric characters

         * If BuyerIdentificationCodeType (6) equals 'INTC' then value must equal 'INTC'

         * If BuyerIdentificationCodeType (6) equals 'NIND' then value must comprise a National Identifier
              of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
              country code and the remaining 33 characters follow that country's National ID format.

         * If BuyerIdentificationCodeType (6) equals 'CCPT' then value must comprise a Passport Number
             of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
             country code and the remaining 33 characters follow that country's Passport Number format.

         * If BuyerIdentificationCodeType (6) equals 'CONCAT' then value must comprise 20 characters of uppercase
           letters, numbers, and #, where the first two characters are letters, next 8 characters are numbers and
           the remaining characters are letters or #, where 11th and 16th character are letters. The birthdate in
           the CONCAT code must match BuyerDateOfBirth (12).

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/Cd is populated then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/Cd
                       ElseIf /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/CdTp = 'INTC' then:
                           'INTC'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/AcctOwnr/Id/LEI
                       /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/AcctOwnr/Id/MIC
                       /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/AcctOwnr/Id/Intl
                       /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/AcctOwnr/Id/Prsn/Othr/Id
                       /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/AcctOwnr/Id/Prsn/Othr/SchmeNm/Cd
                       /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/AcctOwnr/Id/Prsn/Othr/SchmeNm/Prtry


   9  (8)  BuyerCountryOfTheBranch                                                                     (REPEATABLE)

       Branch of the executing firm which received an order from a client.

       This field must be populated where the client of the executing investment firm
       ExecutingEntityIdentificationCode (4) is reported in the BuyerIdentificationCode (8).

       Where this activity was not conducted by a branch this should be populated with the country code of the
       home Member State of the investment firm or the country code of the country where the investment firm has
       established its head office or registered office (in the case of third country firms).

       This field should not be reported where a transaction is executed in a DEAL capacity.

       Where the transaction is for a transmitted order that has met the conditions for transmission set out in
       Article 4, this field must be populated using the information received from the transmitting firm.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) must be provided if field BuyerIdentificationCodeType (6)
                       is one of 'NIND', 'CCPT', 'CONCAT'.

                       Each provided value must comprise a valid 2-digit ISO 3166-2 country code (valid on the
                       transaction date) or 'XS'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/CtryOfBrnch

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/CtryOfBrnch


  10  (9)  BuyerFirstNames                                                                             (REPEATABLE)

       As per Article 7 of RTS22, if the client is a natural person, the transaction report should include
       the full name and date of birth of the client.

       If ReportStatus (1) equals 'NEWT' then the field must contain:

         * A value if BuyerIdentificationCodeType (6) equals one of 'NIND', 'CCPT', 'CONCAT'

         * Blank if BuyerIdentificationCodeType (6) equals one of 'LEI', 'MIC', 'INTC'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/FrstNm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/Id/Prsn/FrstNm


  11  (10)  BuyerSurnames                                                                               (REPEATABLE)

       ( as for BuyerFirstNames (10) )

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/Srnm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/Id/Prsn/Nm


  12  (11)  BuyerDateOfBirth                                                                            (REPEATABLE)

       ( as for BuyerFirstNames (10) )

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each in format YYYY-MM-DD

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/AcctOwnrDtls[j]/Id/BrthDt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/Id/Prsn/BirthDt



  Buyer Decision Maker Details
  ----------------------------

  ( For fields 13 to 18, iterate over /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j] )

  13  (12.1)  BuyerDecisionMakerCodeType                                                                  (REPEATABLE)

       Type of BuyerDecisionMakerCode (15)

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each one of 'LEI', 'NIND', 'CCPT', 'CONCAT'

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j]/Id/CdTp <> 'NIDN' then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j]/Id/CdTp
                       Else:
                           'NIND'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx/New/Buyr/DcsnMakr/Id

       NOTES :         'NIND' - National Identifier
                       'CCPT' - Passport Number
                       'CONCAT' - Concatenation of Nationality, Date of Birth and Name abbreviation


  14  (12.2)  BuyerDecisionMakerNPCode                                                                   (REPEATABLE)

       Used to lookup the associated buyer decision maker identifier held within the ISCI service and
       populate fields 12-15

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  alphanumeric

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j]/ShrtCd

       ISO XML map  :  n/a


  15  (12)  BuyerDecisionMakerCode                                                                      (REPEATABLE)

       Should be set where the client is reported in BuyerIdentificationCode (8) and the client has appointed
       an entity to make their investment decisions on their behalf (under a power of representation).

       Power of representation can be granted by a client that is a natural person or a legal entity and persons
       who have been granted authority to act for the client can also be natural persons or legal entities.

       If the third party is the executing Investment Firm ExecutingEntityIdentificationCode (4), this field
       should be populated with the LEI of the Investment Firm rather than any individual decision maker as
       they will be identified in the InvestmentDecisionWithinFirm field (57 - [TODO] check index!)


       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited list of value(s) which must each match one of the following:

         * If BuyerDecisionMakerCodeType (13) equals 'LEI' then value must comprise a valid LEI code
               as described in ISO 17442 comprising 20 alphanumeric characters

         * If BuyerDecisionMakerCodeType (13) equals 'MIC' then value must comprise a valid MIC code
               as described in ISO 10383 comprising 4 uppercase alphanumeric characters

         * If BuyerDecisionMakerCodeType (13) equals 'INTC' then value must equal 'INTC'

         * If BuyerDecisionMakerCodeType (13) equals 'NIND' then value must comprise a National Identifier
              of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
              country code and the remaining 33 characters follow that country's National ID format

         * If BuyerDecisionMakerCodeType (13) equals 'CCPT' then value must comprise a Passport Number
             of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
             country code and the remaining 33 characters follow that country's Passport Number format

         * If BuyerDecisionMakerCodeType (13) equals 'CONCAT' then value must comprise 20 characters of
           uppercase letters, numbers, and #, where the first two characters are letters, next 8 characters
           are numbers and the remaining characters are letters or #, where 11th and 16th character are
           letters. The birthdate in the CONCAT code must match BuyerDateOfBirth (12)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j]/Id/Cd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/Id/LEI
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/Id/Prsn/Othr/Id
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/Id/Prsn/Othr/SchmeNm/Cd
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/AcctOwnr[j]/Id/Prsn/Othr/SchmeNm/Prtry


  16  (13)  BuyerDecisionMakerFirstNames                                                                   (REPEATABLE)

       First name of each natural person identified as such by BuyerDecisionMakerCodeType (13)

       If ReportStatus (1) equals 'NEWT' then the field must contain:

         * A value if BuyerDecisionMakerCodeType (13) equals one of 'NIND', 'CCPT', 'CONCAT'

         * Blank if BuyerDecisionMakerCodeType (13) equals 'LEI'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j]/Id/FrstNm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/DcsnMakr[i]/Id/Prsn/FrstNm


  17  (14)  BuyerDecisionMakerSurnames                                                                     (REPEATABLE)

       ( as for BuyerDecisionMakerFirstNames(16) )

       Mandatory    :   New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j]/Id/Srnm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/DcsnMakr[j]/Id/Prsn/Nm


  18  (15)  BuyerDecisionMakerDateOfBirth                                                                  (REPEATABLE)

       ( as for BuyerDecisionMakerFirstNames(16) )

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each in format YYYY-MM-DD

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/BuyrDtls/DcsnMkrDtls[j]/Id/BrthDt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/DcsnMakr[j]/Id/Prsn/BirthDt



  Seller Identification & Additional Details
  ------------------------------------------

  ( For fields 19 to 25, iterate over /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j] (for j = 1,…,m) )

  19  (16.1)  SellerIdentificationCodeType                                                                 (REPEATABLE)

       Type of SellerIdentificationCode (21)

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each one of 'LEI', 'MIC', 'INTC', 'NIND', 'CCPT', 'CONCAT'

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/CdTp <> 'NIDN' then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/CdTp
                       Else:
                           'NIND'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id

       NOTES :         'NIND' - National Identifier
                       'CCPT' - Passport Number
                       'CONCAT' - Concatenation of Nationality, Date of Birth and Name abbreviation


  20  (16.2)  SellerNPCode                                                                                 (REPEATABLE)

       Used to lookup the associated seller decision maker identifier held within the ISCI service and
       populate fields 16-20

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  alphanumeric

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/ShrtCd

       ISO XML map  :  n/a


  21  (16)  SellerIdentificationCode                                                                       (REPEATABLE)


       Identification of entity who is selling the instruments

       Mandatory    :  New: Y if SellerIdentificationCodeType (19) is set    Cancel: Blank

       Validation   :  pipe ('|') delimited list of value(s) which must each match one of the following:

         * If SellerIdentificationCodeType (19) equals 'LEI' then value must comprise a valid LEI code
               as described in ISO 17442 comprising 20 alphanumeric characters

         * If SellerIdentificationCodeType (19) equals 'MIC' then value must comprise a valid MIC code
               as described in ISO 10383 comprising 4 uppercase alphanumeric characters

         * If SellerIdentificationCodeType (19) equals 'INTC' then value must equal 'INTC'

         * If SellerIdentificationCodeType (19) equals 'NIND' then value must comprise a National Identifier
              of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
              country code and the remaining 33 characters follow that country's National ID format

         * If SellerIdentificationCodeType (19) equals 'CCPT' then value must comprise a Passport Number
             of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
             country code and the remaining 33 characters follow that country's Passport Number format

         * If SellerIdentificationCodeType (19) equals 'CONCAT' then value must comprise 20 characters of
           uppercase letters, numbers, and #, where the first two characters are letters, next 8 characters
           are numbers and the remaining characters are letters or #, where 11th and 16th character are
           letters. The birthdate in the CONCAT code must match SellerDateOfBirth (25)

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/Cd is populated then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/Cd
                       ElseIf /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/CdTp = 'INTC' then:
                           'INTC'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/LEI
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/MIC
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Intl
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/Othr/Id
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/Othr/SchmeNm/Cd
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/Othr/SchmeNm/Prtry


  22  (17)  SellerCountryOfTheBranch                                                                       (REPEATABLE)

       COuntry code of the seller's branch

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) must be provided if field SellerIdentificationCodeType (19)
                       is one of 'NIND', 'CCPT', 'CONCAT'.

                       Each provided value must comprise a valid 2-digit ISO 3166-2 country code (valid on the
                       transaction date) or 'XS'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/CtryOfBrnch

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Buyr/Sellr/CtryOfBrnch


  23  (18)  SellerFirstNames                                                                               (REPEATABLE)

       First name of each natural person identified as such by SellerIdentificationCodeType (19)

       If ReportStatus (1) equals 'NEWT' then the field must contain:

         * A value if SellerIdentificationCodeType (19) equals one of 'NIND', 'CCPT', 'CONCAT'

         * Blank if SellerIdentificationCodeType (19) equals one of 'LEI', 'MIC', 'INTC'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/FrstNm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/FrstNm


  24  (19)  SellerSurnames                                                                                 (REPEATABLE)

       ( as for SellerFirstNames (23) )

       Mandatory    :   New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/Srnm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/Nm


  25  (20)  SellerDateOfBirth                                                                              (REPEATABLE)

       ( as for SellerFirstNames (23) )

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each in format YYYY-MM-DD

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/AcctOwnrDtls[j]/Id/BrthDt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/BirthDt



  Seller Decision Maker Identification & Additional Details
  ---------------------------------------------------------

  ( For fields 26 to 31, iterate over /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j] (for j = 1,…,m) )


  26  (21.1)  SellerDecisionMakerCodeType                                                                  (REPEATABLE)

       Type of SellerDecisionMakerCode (28)

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each one of 'LEI', 'NIND', 'CCPT', 'CONCAT'

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j]/Id/CdTp <> 'NIDN' then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j]/Id/CdTp
                       Else:
                           'NIND'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/DcsnMakr[j]/Id

       NOTES :         'NIND' - National Identifier
                       'CCPT' - Passport Number
                       'CONCAT' - Concatenation of Nationality, Date of Birth and Name abbreviation


  27  (21.2)  SellerDecisionMakerNPCode                                                                    (REPEATABLE)

       Used to lookup the associated seller decision maker identifier held within the ISCI service and
       populate fields 12-15

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  alphanumeric

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j]/ShrtCd

       ISO XML map  :  n/a


  28  (21)  SellerDecisionMakerCode                                                                        (REPEATABLE)

       Should be set where the client is reported in SellerDecisionMakerCodeType (26) and the client
       has appointed an entity to make their investment decisions on their behalf (under a power of
       representation).

       Power of representation can be granted by a client that is a natural person or a legal entity
       and persons who have been granted authority to act for the client can also be natural persons
       or legal entities.

       If the third party is the executing Investment Firm ExecutingEntityIdentificationCode (4), this
       field should be populated with the LEI of the Investment Firm rather than any individual decision
       maker as they will be identified in the InvestmentDecisionWithinFirm field (57 - [TODO] check index!)

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited list of value(s) which must each match one of the following:

         * If SellerDecisionMakerCodeType (26) equals 'LEI' then value must comprise a valid LEI code
               as described in ISO 17442 comprising 20 alphanumeric characters

         * If SellerDecisionMakerCodeType (26) equals 'MIC' then value must comprise a valid MIC code
               as described in ISO 10383 comprising 4 uppercase alphanumeric characters

         * If SellerDecisionMakerCodeType (26) equals 'INTC' then value must equal 'INTC'

         * If SellerDecisionMakerCodeType (26) equals 'NIND' then value must comprise a National Identifier
              of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
              country code and the remaining 33 characters follow that country's National ID format

         * If SellerDecisionMakerCodeType (26) equals 'CCPT' then value must comprise a Passport Number
             of no more than 35 characters where the first two characters contain a valid 2-digit ISO 3166-2
             country code and the remaining 33 characters follow that country's Passport Number format

         * If SellerDecisionMakerCodeType (26)equals 'CONCAT' then value must comprise 20 characters of
           uppercase letters, numbers, and #, where the first two characters are letters, next 8 characters
           are numbers and the remaining characters are letters or #, where 11th and 16th character are
           letters. The birthdate in the CONCAT code must match BuyerDateOfBirth (12)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j]/Id/Cd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/LEI
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/Othr/Id
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/Othr/SchmeNm/Cd
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/AcctOwnr[j]/Id/Prsn/Othr/SchmeNm/Prtry


  29  (22)  SellerDecisionMakerFirstNames                                                                  (REPEATABLE)

       First name of each natural person identified as such by SellerDecisionMakerCodeType (26)

       If ReportStatus (1) equals 'NEWT' then the field must contain:

         * A value if SellerDecisionMakerCodeType (26) equals one of 'NIND', 'CCPT', 'CONCAT'

         * Blank if SellerDecisionMakerCodeType (26) equals 'LEI'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j]/Id/FrstNm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/DcsnMakr[j]/Id/Prsn/FrstNm


  30  (23)  SellerDecisionMakerSurnames                                                                    (REPEATABLE)

       ( as for SellerDecisionMakerFirstNames (29) )

       Mandatory    :   New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each up to 140 characters comprising uppercase Latin,
                       Cyrillic, Greek, digits 0 - 9, and spedcial characters comma, space, apostrophe,
                       minus, dash

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j]/Id/Srnm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/DcsnMakr[j]/Id/Prsn/Nm


  31  (24)  SellerDecisionMakerDateOfBirth                                                                 (REPEATABLE)

       ( as for SellerDecisionMakerFirstNames (29) )

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  pipe ('|') delimited value(s) each in format YYYY-MM-DD

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/SellrDtls/DcsnMkrDtls[j]/Id/BrthDt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Sellr/DcsnMakr[j]/Id/Prsn/BirthDt



  Tramission Details
  ------------------

  32  (25)  TransmissionOfOrderIndicator

       'true' if conditions for transmission specified in Article 4 were not satisfied, 'false' otherwise

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  Either 'true' or 'false'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrnsmssnDtls/TrnsmssnOrOrdrInd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/OrdrTrnsmssn/TrnsmssnInd

       NOTES        :  Value must be 'false' if field TradingCapacity (36) equals 'DEAL' or 'MTCH'


  33  (26)  TransmittingFirmIdentificationCodeForTheBuyer

       Code used to identify the firm transmitting the order.

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  Valid LEI code as described in ISO 17442 comprising 20 alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrnsmssnDtls/TrnsmttgFrmIdBuyr

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/OrdrTrnsmssn/TrnsmttgBuyr


  34  (27)  TransmittingFirmIdentificationCodeForTheSeller

       Code used to identify the firm transmitting the order

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  Valid LEI code as described in ISO 17442 comprising 20 alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrnsmssnDtls/TrnsmttgFrmIdSellr

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/OrdrTrnsmssn/TrnsmttgSellr



  Transaction Details  ( Transaction Details,,/Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls )
  -------------------

  35  (28)  TradingDateTime

       Trading date time in UTC

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  Format yyyy-MM-ddTHH:mm:ss.ffffffZ with a minimum precision of seconds

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/TradDt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/TradDt


  36  (29)  TradingCapacity

       One of three possible capacities in which the Investment Firm traded for this transaction:

         * DEAL - Dealing on own account

             In this case Investment Firm must be either buyer or seller, and the corresponding seller or buyer
             is the counterparty or client or Trading Venue that the Investment Firm is dealing with

         * MTCH - Matched principal

             This is a transaction where the facilitator interposes itself between the buyer and the seller to the
             transaction such that it is never exposed to market risk throughout the execution of the transaction

         * AOTC - Any other capacity

       ExecutingEntityIdentificationCode (4) equals BuyerIdentificationCode (7) or field SellerIdentificationCode (21)
       if and only if value equales 'DEAL'

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  One of 'DEAL', 'AOTC', 'MTCH'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/TradgCpcty

       ISO XML map  :  /Document/FinInstrmRptgTxRpt[i]/Tx/New/Tx/TradgCpcty


  37  (30.1)  QuantityType

       Quantity Type, one of:

         * 'UNIT' - Units

         * 'NOMI' - Nominal

         * 'MONE' - Monetary

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  One of 'UNIT', 'NOMI', 'MONE'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/Qty/Tp

       ISO XML map  :  /Document/FinInstrmRptgTxRpt[i]/Tx/New/Tx/Qty


  38  (30)  Quantity

       Depending on QuantityType (37) :

         * Number of units of the financial instrument

         * Number of derivative contracts in the transaction

         * Nominal or monetary value of the financial instrument

       For spread bets, the quantity is the monetary value wagered per point movement in the underlying
       financial instrument

       For credit default swaps, the quantity is the notional amount for which the protection is acquired
       or disposed of

       For increase or decrease in notional amount derivative contracts, the value is the absolute value
       of the change

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  Value if provided must be positive. Also if field QuantityType (37) is equal to 'UNIT'
                       then the value must be a decimal number with up to 18 digits of which 17 may be fraction
                       digits; otherwise value must be a decimal number with up to 18 digits of which 5 may be
                       fraction digits

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/Qty/Qty

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Qty/Unit
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Qty/NmnlVal
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Qty/MntryVal


  39  (31)  QuantityCurrency

       A 3-digit ISO 4217 currency code in which the quantity is expressed

       Must be set if and only if QuantityType (37) is one of 'NOMI', 'MONE'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  3-digit ISO 4217 currency code that was active at the trade date or is a pre-EURO
                       currency. Must not contain any of 'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XDR',
                       'XEU', 'XFU', 'XPD', 'XPT', 'XXX'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/Qty/Ccy

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Qty/MntryVal[@Ccy]


  40  (32)  DerivativeNotionalIncreaseDecrease

       Indication as to whether the transaction is an increase or decrease of notional of a derivative contract.

       Set only when there is change in notional for a derivative contract

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  One of 'INCR', 'DECR'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/DerivNtnlChng

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/MntryVal


  41  (33.1)  PriceType

        Price Type of Price (42), one of:

          * 'PERC' - Percentage
          * 'YIEL' - Yield
          * 'BPNT' - Basis Points
          * 'PNDG' - Pending
          * 'NOAP' - Not applicable, e.g. price is gift or transfer between funds/portfolios)
          * 'NA;   - Same as 'NOAP'

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  One of 'PERC', 'YIEL', 'BPNT', 'PNDG', 'NOAP', 'NA'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/Pric/Tp

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric


  42  (33)  Price

       Traded price of the transaction excluding, where applicable, commission and accrued interest

       For option contracts, it is the premium of the derivative contract per underlying or index point

       For spread bets it is the reference price of the underlying instrument

       For credit default swaps (CDS) it is the coupon in basis points

       If price is reported in monetary terms, it is provided in the major currency unit

       If price is currently not available but pending, the value is 'PNDG'

       If price is not applicable the field is empty

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  If PriceType (41) equals 'MONE' then the value must be a decimal number with
                       up to 18 digits of which 13 may be fraction digits

                       If PriceType (41) equals 'BPNT' then the value must be a decimal number with
                       up to 18 digits of which 5 may be fraction digits with a value greater than
                       or equal to 0

                       If PriceType (41) equals 'PERC' or 'YIEL' then the value must be a decimal
                       number with up to 11 digits of which 10 may be fraction digits with a value
                       greater than or equal to 0

                       If PriceType (41 equals 'PNDG' then the value must equal 'PNDG'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/Pric/Pric

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric/Pric/MntryVal/Amt
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric/Pric/MntryVal/Amt/Sgn
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric/Pric/Pctg
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric/Pric/Yld
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric/Pric/BsisPts
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric/NoPric/Pdg


  43  (34)  PriceCurrency

       3-digit ISO 4217 currency code in which Price (42) is expressed if PriceType (41) equals 'MONE'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Valid 3-digit ISO 4217 currency code active at the trade date. Equal to none of
                       'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XDR', 'XEU', 'XFU', 'XPD', 'XPT', 'XXX'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/Pric/Ccy

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/Pric/NoPric/Pdg[@Ccy]


  44  (35)  NetAmount

       Cash amount paid by the buyer of the debt instrument upon the settlement of the transaction.

       This amount equals (clean price * nominal value) + any accrued coupons, and excludes any
       commission or other fees charged to the buyer of the debt instrument

       Value set only when the financial instrument is debt, i.e. CFI = DB**** (Bonds)

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Decimal with up to 18 digits of which 5 may be fraction digits with a value
                       greater than or equal to 0

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/NetAmt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/NetAmt


  45  (36)  Venue

       Where a transaction takes place on a trading venue (venue, OTF or SI) the report for both parties
       should state the MIC of the venue. All other reports in the chain should be populated with 'XOFF'.

       Trading venues outside the EEA should be identified using the relevant segment MIC. Where the
       segment MIC does not exist, use the operating MIC.

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  Valid MIC code as described in ISO 10383 active at the trade date, comprising 4 uppercase
                       alphanumeric Latin characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/TradVn

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/TradVn


  46  (37)  CountryOfTheBranchMembership

       Set for records representing an on-exchange execution i.e. where Venue (45) is a MIC code

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  2-digit ISO 3166-2 country code

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/CtryOfBrnchMmbrshp

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/CtryOfBrnch


  47  (38)  UpfrontPayment

       Signed value of any up-front payment received or paid by the seller

       A payment received by the seller is positive, and negative where the seller pays.

       Must be set if and only if ReportStatus (1) equals 'NEWT' and either DerivativeNotionalIncreaseDecrease (???)
       is set or InstrumentClassification (???) starts with 'SC'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Decimal with up to 18 digits of which 5 may be fraction digits

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/UpFrntPmt/Amt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/UpFrntPmt/Amt
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/UpFrntPmt/Amt/Sgn


  48  (39)  UpfrontPaymentCurrency

       3-digit ISO 4217 currency code of UpfrontPayment (47) set if and only latter is set

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  valid 3-digit ISO 4217 currency code active at the trade date. Equal to none of
                       'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XDR', 'XEU', 'XFU', 'XPD', 'XPT', 'XXX'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/UpFrntPmt/Ccy

       ISO XML map :  /Document/FinInstrmRptgTxRpt/Tx/New/Tx[i]/UpFrntPmt/Amt[@Ccy]


  49  (40)  ComplexTradeComponentId

       Identifier, internal to the reporting firm to identify all the reports related to the same execution
       of a combination of financial instruments in accordance with Article 12. The code must be unique at
       the level of the firm for the group of reports related to the execution.

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  up to 35 uppercase Latin alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TxDtls/CmplxTradCmpntId

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/CmplxTradCmpntId



  Intrument Details  ( /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls )
  -----------------

  50  (41)  InstrumentIdentificationCode

       For ETDs and exchange traded securities traded this field should be populated with the ISIN used to
       identify that product.

       For OTC products, i.e. where Venue (45) equals 'XXXX', this field should be left blank and fields
       51 to 66 should be set to describe the product. But otherwise, i.e. if Venue (45) is an EEA trading
       venue, then the value should be set

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  valid 12-character ISO 6166 ISIN code

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/Id

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Id
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/FinInstrmGnlAttrbts/Id


  51  (42)  InstrumentFullName

       Full name of the financial instrument

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if Venue (45) equals 'XXXX'
                       Value must be up to 350 characters comprising of upper case Latin letters [A-Z],
                       digits [0-9] and special characters: percentage, question mark, number sign, space,
                       plus and forward slash [%?# +/]

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/FullNm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/FinInstrmGnlAttrbts/FullNm


  52  (43)  InstrumentClassification

       Taxonomy used to classify the financial instrument.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if Venue (45) equals 'XXXX'
                       Value if set is a complete and accurate CFI code confirming to ISO 10962:2015.
                       It comprises 6 uppercase Latin characters, matching one of the following:

                         *  One of O*E***, H**A**, H**D**, H**G** if OptionExerciseStyle (63) equals 'EURO'
                         *  One of O*A***, H**B**, H**E**, H**H** if OptionExerciseStyle (63) equals 'AMER'
                         *  One of O*B***, H**C**, H**F**, H**I** if OptionExerciseStyle (53) equals 'BERM'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/ClssfctnCd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/FinInstrmGnlAttrbts/ClssfctnTp


  53  (44)  NotionalCurrency1

       Currency code in which the notional is denominated

       For interest rate or currency derivatives contract, this will be the notional currency of leg 1 or the
       currency 1 of the pair

       For swaptions where the underlying swap is single-=currency, this is the notional currency of the
       underlying swap. For swaptions where the underlying is multi-=currency, this is the notional currency
       of leg 1 of the swap.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of:
                         O*****, S*****, C*****, R*****, F*****, E*****, D*****, H*****, J*****

                       If set then must be valid 3-digit ISO 4217 currency code active at the trade date
                       or a pre-EURO currency and none of:
                         'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XDR', 'XEU', 'XFU', 'XPD', 'XPT', 'XXX'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/NtnlCcs/NtnlCcy1

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/FinInstrmGnlAttrbts/NtnlCcy


  54  (45)  NotionalCurrency2

       Currency code

       For multi-currency or cross-currency swaps the currency in which leg 2 of the contract is denominated

       For swaptions where the underlying swap is multi-currency, the currency in which leg 2 of the swap is
       denominated

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of
                         SF****, FFC***

                       Must be blank if either NotionalCurrency1 (53) is blank or InstrumentClassification (52)
                       matches one of: O**S**, O**D**, O**T**, O**N**, FFS***, FFD***, FFN***, FFV***, FC****,
                       ST****, HT****, HE****, HF****, R*****, E*****, C*****, D***** , J*****

                       If set then must be valid 3-digit ISO 4217 currency code active at the trade date
                       or a pre-EURO currency and none of:
                         'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XDR', 'XEU', 'XFU', 'XPD', 'XPT', 'XXX'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/NtnlCcs/NtnlCcy2

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/FinInstrmGnlAttrbts/OthrLegCcy


  55  (46)  PriceMultiplier

       Number of units of the underlying instrument represented by a single derivative contract.

       Monetary value covered by a single swap contract where the quantity field indicates the number of swap
       contracts in the transaction.

       For a future or option on an index, the amount per index point.

       For spreadbets the movement in the price of the underlying instrument on which the spreadbet is based.

       Value must be consistent with Quantity (38) and Price (42)

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if Venue (45) equals 'XXXX'
                       Must be blank if Venue (45) equals 'XOFF'
                       Decimal with up to 18 digits of which 17 may be fraction digits with a value greater than 0

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/PricMltplr

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/PricMltplr


  56  (47)  UnderlyingInstrumentCode                                                                       (REPEATABLE)

       ISIN for OTC derivative products (venue = 'XXXX') to inform the regulator of the direct underlying instrument.

       For ADRs, GDRs and similar instruments, the ISIN code of the financial instrument on which those instruments
       are based.

       For convertible bonds, the ISIN code of the instrument in which the bond can be converted.

       For derivatives or other instruments which have an underlying, the underlying instrument ISIN code, when
       the underlying is admitted to trading, or traded on a trading venue. Where the underlying is a stock
       dividend, then ISIN code of the related share entitling the underlying dividend.

       For Credit Default Swaps, the ISIN of the reference obligation shall be provided.

       In case the underlying is an Index and has an ISIN, the ISIN code for that index.

       Where the underlying is a basket, include the ISIN of each constituent of the basket that is admitted to
       trading or is traded on a trading venue. Field 47 shall be reported as many times as necessary to list
       all reportable instruments in the basket.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if Venue (45) equals 'XXXX'
                       pipe ('|') delimited list of valid 12-character ISO 6166 ISIN code(s)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/
                           UndrlygInstrmDtls/Id[j] (for j = 1,…,m)

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/UndrlygInstrm


  57  (48)  UnderlyingIndexName

       Underlying index or name.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of:
                         O**I**, O**N**, FFI***, FFN***
                       Must be blank if InstrumentClassification (52) matches one of:
                         DB****, DT****, DY****, E*****
                       Must be up to 25 characters consisting of upper case Latin letters [A-Z], digits [0-9]
                       and special characters: percentage, question mark, number sign, space, plus, slash [%?# +/]

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/UndrlygInstrmDtls/IndxDtls/Nm

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/
                           UndrlygInstrm/Indx/Nm


  58  (49)  TermOfTheUnderlyingIndex

       Term of the underlying index.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of:
                         O**N**, FFN***
                       Must be blank if UnderlyingIndexName (57) is blank
                       Must be integer number of up to 3 digits followed by either 'DAYS', 'WEEK', 'MNTH', 'YEAR'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/UndrlygInstrmDtls/IndxDtls/Trm

       ISO XML map  : /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/UndrlygInstrm/
                         Indx/Nm/RefRate/Term


  59  (50)  OptionType

       Indication as to whether the derivative contract is a call (right to purchase a specific underlying asset)
       or a put (right to sell a specific underlying asset) or whether this cannot be determined at the time of
       execution.

       In case of swaptions it will be one of:

         *  'PUTO', in case of receiver swaption, in which the buyer has the right to enter into a swap as a
             fixed-rate receiver

         *  'CALL', in case of payer swaption, in which the buyer has the right to enter into a swap as a
             fixed-rate payer

       In case of Caps and Floors it will be one of:

         * 'PUTO', in case of a Floor
         * 'CALL', in case of a Cap

       The value applies only to derivatives that are options or warrants

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of
                         O*****, H*****, RW****
                       Must be blank if InstrumentClassification (52) matches one of
                         F*****, S*****, E*****, C*****, D*****, J*****
                       Set value must equal:
                         *  'CALL' if InstrumentClassification (52) matches one of
                             OC****, H**A**, H**B**, RW**C*, H**C**

                         *  'PUTO' if InstrumentClassification (52) matches one of
                            OP****, H**D**, H**E**, RW**P*, H**F**

                         *  'OTHR' if InstrumentClassification (52) matches one of
                            OM****, H**G**, H**H**, RW**B*, H**I**

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/OptnDtls/Optn

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/OptnTp


  60  (51.1)  StrikePriceType

       Strike Price type, one of:

         * 'MONE' - Monetary
         * 'PERC' - Percentage
         * 'YIEL' - Yield
         * 'BPNT' - Basis points
         * 'PNDG' - Pending"

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of
                         O*****, H*****, RW****
                       Must be bn=lank if InstrumentClassification (52) matches one of
                         F*****, S*****, E*****, C*****, D*****, J*****

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/OptnDtls/StrkPric/Tp

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric


  61  (51)  StrikePrice

       Pre-determined price at which the holder will have to buy or sell the underlying instrument, or an indication
       that the price cannot be determined at the time of execution.

       Value applies only to an option or warrant where strike price can be determined at the time of execution.

       Where price is currently not available but pending, the value is blank

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if and only if StrikePriceType (60) is one of
                         'MONE', 'PERC', 'YIEL', 'BPNT'

                       Value if set must match one of:

                         * If StrikePriceType (60) equals 'MONE' then value must be a decimal number
                           with up to 18 digits of which 13 may be fraction digits

                         * If StrikePriceType (60) equals 'PERC' or 'YIEL' then the value must be a non-negative
                           decimal number with up to 11 digits of which 10 may be fraction digits

                         * If StrikePriceType (60) equals 'BPNT' then the value must be a non-negative
                           decimal number with up to 18 digits of which 17 may be fraction digits

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/OptnDtls/StrkPric/Pric

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Amt

                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Amt/Sgn

                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Pric/Pctg

                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Pric/Yld

                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Pric/BsisPts

                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Pric/Pdg


  62  (52)  StrikePriceCurrency

       Currency code of the strike price

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if & only if StrikePriceType (60) equals 'MONE'

                       Value if set must be valid 3-digit ISO 4217 currency code active at the trade date,
                       and none of
                         'XAG', 'XAU', 'XBA', 'XBB', 'XBC', 'XBD', 'XDR', 'XEU', 'XFU', 'XPD', 'XPT', 'XXX'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/OptnDtls/StrkPric/Ccy

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Amt[@Ccy]

                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/StrkPric/
                           Pric/MntryVal/Pric/Pdg[@Ccy]


  63  (53)  OptionExerciseStyle

       Indication as to when the option may be exercised, one of:

         * 'EURO' - European - fixed date
         * 'AMER' - American - any time during the life of the contract
         * 'ASIA' - Asian - fixed date
         * 'BERM' - Bermudan - series of pre-specified dates
         * 'OTHR' - Any other type

       Applicable only to options, warrants and entitlement certificates

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of
                         O*****, H*****, RW****

                       Must be blank if InstrumentClassification (52) matches one of
                         F*****, S*****, E*****, C*****, D*****, J*****

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/OptnDtls/OptnExcrStyle

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/OptnExrcStyle


  64  (54)  MaturityDate

       Maturity Date of the financial debt instrument with a defined maturity

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of
                         D*****

                       Must be blank if InstrumentClassification (52) matches one of
                         R*****, O*****, F*****, S*****, E*****, C*****, H*****, J*****

                       Value if set must have format yyyy-MM-dd and be not before field TradingDateTime (35)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/MtrtyDt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DebtInstrmAttrbts/MtrtyDt


  65  (55)  ExpiryDate

      Expiry Date of the financial debt instrument with a defined expiry

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if InstrumentClassification (52) matches one of
                         O*****, F*****, JC**F*

                       Must be blank if InstrumentClassification (52) matches one of
                         E*****, C*****, D*****

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/XpryDt

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DerivInstrmAttrbts/XpryDt


  66  (56)  DeliveryType

       Indication as to whether the transaction is settled physically or in cash, one of:

         *  'PHYS' - Physically settled
         *  'CASH' - Cash settled
         *  'OPTL' - Optional for counterparty or when determined by a third party

       Set to 'OPTL' if the value cannot be determined at time of execution

       Applicable only to derivatives.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if Venue (45) equals 'XXXX'

                       Must equal one of:

                         * 'PHYS' if InstrumentClassification (52) matches one of
                             OC**P*, OP**P*, FF*P**, FC*P**, SR***P, ST***P, SE***P, SC***P, SF***P, SM***P,
                             HR***P, HT***P, HE***P, HC***P, HF***P, HM***P, IF***P, JE***P, JF***P, JC***P,
                             JR***P, JT***P, LL***P

                         * 'CASH' if InstrumentClassification (52) matches one of
                             OC**C*, OP**C*, FF*C**, FC*C**, SR***C, ST***C, SE***C, SC***C, SM***C, HR***C,
                             HT***E, HE***C, HC***C, HF***C, HM***C, JE***C, JF***C, JC***C, JR***C, JT***C,
                             LL***C

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/InstrmDtls/InstrmDscrptn/DlvryTp

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/Tx/FinInstrm/Othr/DlvryTp



  Trader, Algorithms, Waivers, & Indicators  ( /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds )
  -----------------------------------------

  67  (57.1)  InvestmentDecisionWithinFirmType

       Type of Investment decision within firm, one of:

         * 'ALGO' - Algorithm
         * 'NIND' - National Identifier
         * 'CCPT' - Passport Number
         * 'CONCAT' - Concatenation of Nationality, Date of Birth and Name abbreviation

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  Must be set if and only if one or more of:

                         * TradingCapacity (36) equals 'DEAL'

                         * TradingCapacity (36) equals one of 'MTCH', 'AOTC' and
                                  BuyerIdentificationCodeType (6) equals 'LEI'
                           and/or SellerIdentificationCodeType (19) equals 'LEI'

                         * TradingCapacity (36) equals 'AOTC' and
                              ExecutingEntityIdentificationCode (4) equals BuyerDecisionMakerCode (15)  or
                              ExecutingEntityIdentificationCode (4) equals SellerDecisionMakerCode (28)

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/InvstmtDcsnWthnFrmDtls/
                                                                                               Id/CdTp <> 'NIDN' then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/InvstmtDcsnWthnFrmDtls/Id/CdTp
                       Else:
                           'NIND'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/InvstmtDcsnPrsn/Algo
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/InvstmtDcsnPrsn/Prsn


  68  (57.2)  InvestmentDecisionWithinFirmNPCode

       Investment decision within firm NP code

       If a code is provided then it will be used to lookup against the ISCI service and populate theInvestment
       decision within firm fields as refernced within the ISCI specification document

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  Up to 52 alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/InvstmtDcsnWthnFrmDtls/ShrtCd

       ISO XML map  :  n/a


  69  (57)  InvestmentDecisionWithinFirm

      Investment decision within firm

      Set if and only if one of the following applies:

        * The Investment Firm is dealing on own account
        * The Investment Firm is making an investment decision for a client acting under a discretionary mandate

      i.e. it is set if any of the following applies:

        * TradingCapacity (36) equals 'DEAL'

        * TradingCapacity (36) equals either 'MTCH' or 'AOTC', and either BuyerIdentificationCodeType (6)
          equals 'LEI'  or SellerIdentificationCodeType (19) equals 'LEI'

        * TradingCapacity (36) equals 'AOTC', and ExecutingEntityIdentificationCode (4) equals
          BuyerDecisionMakerCode (15) or equals SellerDecisionMakerCode (28)

      If set then the value must be:

        * If InvestmentDecisionWithinFirmType (67) equals 'ALGO' - up to 50 uppercase Latin alphanumeric characters

        * If InvestmentDecisionWithinFirmType (67) equals 'NIND' - National Identifier of no more than 35 characters
          where the first two characters are a valid 2-digit ISO 3166-2 country code valid on the transaction date
          and the remaining 33 characters follow that country's National ID format.

        * If InvestmentDecisionWithinFirmType (67) equals 'CCPT' - Passport Number of no more than 35 characters
          where the first two characters are a valid 2-digit ISO 3166-2 country code and the remaining 33 characters
          follow that country's Passport Number format.

        * If InvestmentDecisionWithinFirmType (67) equals 'CONCAT' - exactly 20 characters of capital Latin letters,
          numbers and #, where first two characters are letters, the next 8 characters are numbers and the remaining
          characters are letters or #, where 11th and 16th character are letters.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  (see above)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/InvstmtDcsnWthnFrmDtls/Id/Cd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/InvstmtDcsnPrsn/Prsn/Othr/Id
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/InvstmtDcsnPrsn/Prsn/Othr/SchmeNm/Cd
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/InvstmtDcsnPrsn/Prsn/Othr/SchmeNm/Prtry


  70  (58)  CountryOfTheBranchResponsibleForThePersonMakingTheInvestmentDecision

      Country of the branch responsible for  the person  making the investment decision,

      No value for this is required when InvestmentDecisionWithinFirm (69) represents an algorithm. Otherwise
      the value should be the country code of the branch of the investment firm to which the individual stated
      in field 58 (??) is associated.

      Where the person responsible for the investment decision was not supervised by a branch, this field should
      be the country code of the home Member State of the investment firm or the country code of the country where
      the firm has established its head office or registered office (in the case of third country firms).

      Must be set if ReportStatus (1) equals 'NEWT' and InvestmentDecisionWithinFirmType (67) is one of
      'NIND', 'CCPT', 'CONCAT'

      Must be blank if ReportStatus (1) equals 'NEWT' and InvestmentDecisionWithinFirmType (67) is none of
      'NIND', 'CCPT', 'CONCAT' or if ReportStatus (1) equals 'CANC' and InvestmentDecisionWithinFirmType (67)
      equals 'ALGO'

       Mandatory    :  New: Conditional     Cancel: Conditional

       Validation   :  2-digit ISO 3166-2 country code

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/InvstmtDcsnWthnFrmDtls/
                           CtryOfRspnsblBrnch

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/InvstmtDcsnPrsn/Prsn/CtryOfBrnch


  71  (59.1)  ExecutionWithinFirmType

       Type of execution within firm, one of:

         * 'ALGO' - Algorithm
         * 'NIND' - National Identifier
         * 'CCPT' - Passport Number
         * 'CONCAT' - Concatenation of Nationality, Date of Birth and Name abbreviation
         * 'CLIENT'

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  (One of above values)

       SAXO XML map :  If /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/ExctWthnFrmDtls/
                                                                                               Id/CdTp <> 'NIDN' then:
                           /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/ExctWthnFrmDtls/Id/CdTp
                       Else:
                           'NIND'

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/ExctgPrsn/Algo
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/ExctgPrsn/Prsn


  72  (59.2)  ExecutionWithinFirmNPCode

       Execution within firm NP code, a value used to lookup the associated Execution within firm identifier held
       within the ISCI service

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  Up to 52 alphanumeric characters

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/ExctWthnFrmDtls/ShrtCd

       ISO XML map  :  n/a


  73  (59)  ExecutionWithinFirm

       Indicates to the regulator who/what made the decision of where to execute the transaction.

       Must be set if and only if:
         ReportStatus (1) equals 'NEWT' and ExecutionWithinFirmType (71) is one of 'NIND', 'CCPT', 'CONCAT', 'ALGO'

       If set then the value must be:

        * If ExecutionWithinFirmType (71) equals 'ALGO' - up to 50 uppercase Latin alphanumeric characters

        * If ExecutionWithinFirmType (71) equals 'NIND' - National Identifier of no more than 35 characters where
          the first two characters are a valid 2-digit ISO 3166-2 country code valid on the transaction date and
          the remaining 33 characters follow that country's National ID format.

        * If ExecutionWithinFirmType (71) equals 'CCPT' - Passport Number of no more than 35 characters where the
          first two characters are a valid 2-digit ISO 3166-2 country code and the remaining 33 characters follow
          that country's Passport Number format.

        * If ExecutionWithinFirmType (71) equals 'CONCAT' - exactly 20 characters of capital Latin letters, numbers
          and #, where first two characters are letters, the next 8 characters are numbers & the remaining characters
          are letters or #, where 11th and 16th character are letters.

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  (see above)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/ExctWthnFrmDtls/Id/Cd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/ExctgPrsn/Prsn/Othr/Id
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/ExctgPrsn/Prsn/Othr/SchmeNm/Cd
                       /Document/FinInstrmRptgTxRpt/Tx[i]/New/ExctgPrsn/Prsn/Othr/SchmeNm/Prtry


  74  (60)  CountryOfTheBranchSupervisingThePersonResponsibleForTheExecution

      Country of the branch supervising the person responsible for the execution

      Not required when ExecutionWithinFirm (73) indicates an algorithm ('ALGO'). Otherwise it must be the country
      code of the branch of the investment firm with which the individual indicated by ExecutionWithinFirm (73) is
      associated.

      Where the person responsible was not supervised by a branch, the value must be the country code of the home
      Member State of the investment firm, or the country code of the country where the firm has established its
      head office or registered office (in the case of third country firms)

      Must be set if and only if ExecutionWithinFirmType (71) is one of 'NIND', 'CCPT', 'CONCAT'

       Mandatory    :  New: Conditional     Cancel: Blank

       Validation   :  valid 2-digit ISO 3166-2 country code or 'XS'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/ExctWthnFrmDtls/CtryOfSprvsngBrnch

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/ExctgPrsn/Prsn/CtryOfBrnch


  75  (61)  WaiverIndicator                                                                                (REPEATABLE)

      Waiver indicator

      Required only executions on the market (i.e. where Venue (45) is reported with a MIC. For all other
      executions this field can be left blank.

      Market operators are required to publish bid-offer spreads during market hours as part of their pre-trade
      transparency requirements (MiFIR Article 3). In certain circumstances, these pre-trade transparency
      requirements can be waived by a competent authority (MiFIR Article 4).

      This field should be populated when an execution on the market is relating to a waived pre-trade transparency
      requirement as follows;

        * For all instruments:

            * 'RFPT' = Reference price transaction

            * 'NLIQ' = Negotiated transactions in liquid financial instruments

            * 'OILQ' = Negotiated transactions in illiquid financial instruments

            * 'PRIC' = Negotiated transactions subject to conditions other than the current market price
                       of that equity financial instrument.

        * For non-equity instruments:

            * 'SIZE' = Above specific size transaction
            * 'ILQD' = Illiquid instrument transaction",

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  pipe ('|') delimited list of value(s) each one of 'RFPT', 'NLIQ', 'OILQ', 'PRIC', 'SIZE', 'ILQD'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/WvrInd[j] (for j = 1,…,m)

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/AddtlAttrbts/WvrInd


  76  (62)  ShortSellingIndicator

       Short selling indicator

       If set then must be one of:

         * 'SESH' - Short sale with no exemption
         * 'SSEX' - Short sale with exemption
         * 'SELL' - No short sale
         * 'UNDI' – Information not available

       Required when the investment firm's execution is a short sell (either on their own behalf or on behalf
       of a client). In this case this field should equal 'SESH'.

       Short selling as part of market making or primary market activity should be identified with 'SSEX'.

       For aggregated order, the short selling flag is only required on the client side allocation, not the
       aggregated market side leg.

       Where the short selling information is not made available to the Investment Firm by the client, this
       field should be populated with 'UNDI'.

       Abide are looking for clarification from ESMA as to when 'SELL' should be reported in this field

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  (see above)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/ShrtSellgInd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/AddtlAttrbts/ShrtSellgInd


  77  (63)  OTCPostTradeIndicator                                                                          (REPEATABLE)

      OTC post-trade indicator

      Indicator as to the type of transaction in accordance with Articles 20(3)(a) and 21(5)(a) of
      Regulation (EU) 600/2014 :

        * For all instruments:

            * 'BENC' = Benchmark transactions
            * 'ACTX' = Agency cross transactions
            * 'LRGS' = Post-trade large-in-scale transactions
            * 'ILQD' = Illiquid instrument transaction
            * 'SIZE' = Above specific size transaction
            * 'CANC' = Cancellations
            * 'AMND' = Amendments

        * For equity instruments:

            * 'SDIV' = Special dividend transactions
            * 'RPRI' = Transactions which have received price improvement
            * 'DUPL' = Duplicative trade reports
            * 'TNCP' = Transactions not contributing to the price discovery process for the purposes
                       of Article 23 of Regulation (EU) No 600/2014

        * For non-equity instruments:

            * 'TPAC' = Package transaction
            * 'XFPH' = Exchange for Physical transaction",

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  pipe ('|') delimited list of value(s) each one of 'BENC', 'ACTX', 'LRGS', 'ILQD',
                       'SIZE', 'CANC', 'AMND', 'SDIV', 'RPRI', 'DUPL', 'TNCP', 'TPAC' or 'XFPH'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/
                           OTCPostTradeIndicator[j] (for j = 1,…,m)

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/AddtlAttrbts/OTCPstTradInd


  78  (64)  CommodityDerivativeIndicator

       Commodity derivative indicator

       In an attempt to reduce prevent market abuse and support orderly pricing and settlement in the
       on exchange commodity markets, ESMA have introduced limits to position sizes which can be held
       by individuals. (See MiFID 2: Article 57).

       Where the executions is a hedge trade it doesn't count towards this limit. As such, where trading
       a commodity instrument, it should be indicated here if it is a hedge/reducing risk (this field
       should be populated as 'true').

       Mandatory    :  New: No     Cancel: Blank

       Validation   :  either 'true' or 'false'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/CmmdtsDrvtvInd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/AddtlAttrbts/RskRdcgTx


  79  (65)  SecuritiesFinancingTransactionIndicator

       Securities financing transaction indicator

       Set where the transaction falls within the scope of activity but is exempted from reporting under
       [Securities Financing Transactions Regulation].

       Mandatory for commodity derivative transaction where the InstrumentIdentificationCode (50) is
       classified in instrument reference data as commodity derivative (i.e. field 4 in the instrument
       reference data static file equals 'true')

       Mandatory    :  New: Yes     Cancel: Blank

       Validation   :  either 'true' or 'false'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/TrdrAlgrthmsWvrsAndInds/SctiesFincgTxInd

       ISO XML map  :  /Document/FinInstrmRptgTxRpt/Tx[i]/New/AddtlAttrbts/SctiesFincgTxInd,Field



  Eligibility Determination  ( /Document/NRRMiFIRTxRpt/Tx[i]/New/ElgbltyDtrmntnAttrbts )
  -------------------------

  80  (66)  BranchLocation

       Entity branch location for 'MiFID Investment Firm' eligibility check

       Mandatory    :  New: No     Cancel: No

       Validation   :  2-digit ISO 3166-2 country code or 'XS'

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/ElgbltyDtrmntnAttrbts/BrnchLctn

       ISO XML map  :  n/a


  81  (67)  TransactionType

       Transaction Type

       Used to determine MiFID reportability for different transaction types

       For Mifid transactions, must be one of following if set:

         * 'GUST' = Give-up for Settlement
         * 'GIST' = Give-in for Settlement
         * 'CUMV' = Custodial Movement
         * 'ITFR' = Internal Transfer
         * 'REPO' = Repo or Equity Finance
         * 'REDM' = Redemption of UCITS
         * 'ETRM' = Early Termination re Novation
         * 'NOVA' = Novation/Assignment
         * 'EXER' = Trade Post Option Exercise
         * 'OPCA' = Optional Corporate Action
         * 'IVCA' = Involuntary Corporate Action
         * 'EMSP' = Small Employee Share Purchase",N,N,,"'GUST'
         * 'GIST'
         * 'CUMV'
         * 'ITFR'
         * 'REPO'
         * 'REDM'
         * 'ETRM'
         * 'NOVA'
         * 'EXER'
         * 'OPCA'
         * 'IVCA'
         * 'EMSP'

       Mandatory    :  New: No     Cancel: No

       Validation   :  (see above)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/ElgbltyDtrmntnAttrbts/TxTp

       ISO XML map  :  n/a


  82  (68)  LifecycleEvent

       MiFID reportability for different Lifecycle event

       For Mifid transactions, must be one of following if set:

         * 'AC' = Accretion
         * 'AM' = Amortization
         * 'CL' = Cleared
         * 'CA' = Corporate Action Affecting Underlying Instrument
         * 'CE' = Credit Event
         * 'D' = Decrease
         * 'FN' = Full Novation
         * 'FT' = Full Termination
         * 'I' = Increase
         * 'N' = Novation
         * 'NT' = Novation-Trade
         * 'PN' = Partial Novation
         * 'PT' = Partial Termination
         * 'PC' = Portfolio Compression
         * 'SE' = Succession Event",N,N,,"'AC'
         * 'AM'
         * 'CL'
         * 'CA'
         * 'CE'
         * 'D'
         * 'EX'
         * 'FN'
         * 'FT'
         * 'I'
         * 'N'
         * 'NT'
         * 'PN'
         * 'PT'
         * 'PC'
         * 'SE'

       Mandatory    :  New: No     Cancel: No

       Validation   :  (see above)

       SAXO XML map :  /Document/NRRMiFIRTxRpt/Tx[i]/New/ElgbltyDtrmntnAttrbts/LfcclEvnt

       ISO XML map  :  n/a

'''

xml_namespace_tag = None

delim = '|'  # pipe

# Report Details
#
ind_report_status     = 0
ind_trans_ref_no      = 1
ind_trans_id_code     = 2
ind_entity_id_code    = 3
ind_cover_201465eu    = 4

# Buyer account details
#
ind_buy_acct_id_type  = 5
ind_buy_acct_np_code  = 6
ind_buy_acct_id_code  = 7
ind_buy_acct_country  = 8
ind_buy_acct_forename = 9
ind_buy_acct_surname  = 10
ind_buy_acct_birthdt  = 11

# Buyer Decision Maker details
#
ind_buy_dcsn_id_type  = 12
ind_buy_dcsn_np_code  = 13
ind_buy_dcsn_id_code  = 14
ind_buy_dcsn_forename = 15
ind_buy_dcsn_surname  = 16
ind_buy_dcsn_birthdt  = 17

# Seller account details
#
ind_sel_acct_id_type  = 18
ind_sel_acct_np_code  = 19
ind_sel_acct_id_code  = 20
ind_sel_acct_country  = 21
ind_sel_acct_forename = 22
ind_sel_acct_surname  = 23
ind_sel_acct_birthdt  = 24

# Seller Decision Maker details
#
ind_sel_dcsn_id_type  = 25
ind_sel_dcsn_np_code  = 26
ind_sel_dcsn_id_code  = 27
ind_sel_dcsn_forename = 28
ind_sel_dcsn_surname  = 29
ind_sel_dcsn_birthdt  = 30

# Transmission details
#
ind_trnsm_order_ind   = 31
ind_trnsm_buy_id_code = 32
ind_trnsm_sel_id_code = 33

# Transaction details
#
ind_trnsc_datetime    = 34
ind_trnsc_trade_cap   = 35
ind_trnsc_qty_type    = 36
ind_trnsc_qty_val     = 37
ind_trnsc_qty_ccy     = 38
ind_trnsc_drv_notion  = 39
ind_trnsc_prc_type    = 40
ind_trnsc_prc_val     = 41
ind_trnsc_prc_ccy     = 42
ind_trnsc_net_amt     = 43
ind_trnsc_venue       = 44
ind_trnsc_brnch_ctry  = 45
ind_trnsc_up_fr_amt   = 46
ind_trnsc_up_fr_ccy   = 47
ind_trnsc_cmpnt_id    = 48

# Instrument details
#
ind_instr_id_code     = 49
ind_instr_full_name   = 50
ind_instr_class       = 51
ind_instr_notnl_ccy1  = 52
ind_instr_notnl_ccy2  = 53
ind_instr_price_mult  = 54
ind_instr_under_code  = 55
ind_instr_under_name  = 56
ind_instr_under_term  = 57
ind_instr_optn_type   = 58
ind_instr_strk_type   = 59
ind_instr_strk_price  = 60
ind_instr_strk_ccy    = 61
ind_instr_optn_exrc   = 62
ind_instr_mat_date    = 63
ind_instr_exp_date    = 64
ind_instr_dlvry_type  = 65

# Trading details
#
ind_trade_invst_type  = 66
ind_trade_invst_np    = 67
ind_trade_invst_code  = 68
ind_trade_invst_ctry  = 69
ind_trade_exec_type   = 70
ind_trade_exec_np     = 71
ind_trade_exec_code   = 72
ind_trade_exec_ctry   = 73
ind_trade_waiver_ind  = 74
ind_trade_shrt_ind    = 75
ind_trade_post_ind    = 76
ind_trade_drv_ind     = 77
ind_trade_sec_ind     = 78

# Eligibility details
#
ind_elig_branch_loc   = 79
ind_elig_trnsc_type   = 80
ind_elig_cycle_event  = 81

output_csv_file = None

number_of_columns = 82

out_row = [''] * number_of_columns


def xml_find(xml_ref, in_str):

    global xml_namespace_tag

    return xml_ref.find(xml_namespace_tag + in_str)


# returns the tag name under the specified tag tree
def tag_from_tree(xml_ref, *tag_names):
    if len(tag_names) == 0:
        return xml_ref

    for tag_name in tag_names:
        xml_tx_new_element = xml_find(xml_ref, tag_name)
        xml_ref = xml_tx_new_element

        if xml_tx_new_element is None:
            return ""

    return xml_tx_new_element


def xml_get(xml_ref, in_str, attr):

    global xml_namespace_tag

    xml_ref = xml_ref.find(xml_namespace_tag + in_str)

    return '' if xml_ref is None or xml_ref.attrib[attr] is None else xml_ref.attrib[attr]


def xml_find_text(xml_ref, in_str):

    global xml_namespace_tag

    xml_ret = xml_ref.find(xml_namespace_tag + in_str)

    # Annoyingly, text for an empty block, such as <fred></fred> can return None instead of ""
    return '' if xml_ret is None or xml_ret.text is None else xml_ret.text


# returns the content within a tag under the specified tag tree
def get_tag_content(xml_ref, *tag_names):

    for tag_name in tag_names:
        xml_tx_new_element = xml_find(xml_ref, tag_name)
        xml_tx_new_content = xml_find_text(xml_ref, tag_name)

        xml_ref = xml_tx_new_element
        if xml_tx_new_element is None or xml_tx_new_content is None:
            return ""

    return xml_tx_new_content


def xml_findall(xml_ref, in_str):

    global xml_namespace_tag

    return xml_ref.findall(xml_namespace_tag  + in_str)


# get inputs from the config file, -clnt-mode
def get_clnt_mode():

    config_file_ref = args.clnt_mode
    if config_file_ref is not None:
        if re.match(r'.*\.csv$', config_file_ref):
            config_file = codecs.open(config_file_ref, 'r', 'utf-8')
            get_csv_rows = csv.reader(config_file)

            row_number = 0
            for row in get_csv_rows:
                row_number += 1
                # set value
                if row_number == 2:
                    return row[0]

    return ''


# returns a list of all the none empty values contained within given tag and its children
def get_values(tag):
    value_list = []
    for value in tag.itertext():
        value = value.strip('\n')
        value = value.strip(' ')
        if value != '':
            value_list.append(value)

    return value_list


# returns a list of all the none empty tags contained within (not incl.) the given tag and its children
def get_tags(tag):
    tag_list = []
    for single_tag in tag.iter():
        tag_text = single_tag.text
        if tag_text is not None:
            tag_text = tag_text.strip('\n')
            tag_text = tag_text.strip(' ')
        if tag_text != '':
            tag_list.append(single_tag)

    return tag_list


def get_output_header_row():

    global out_row

    # Report Details
    #
    out_row[ind_report_status]     = 'report_status'
    out_row[ind_trans_ref_no]      = 'trans_ref_no'
    out_row[ind_trans_id_code]     = 'trans_id_code'
    out_row[ind_entity_id_code]    = 'entity_id_code'
    out_row[ind_cover_201465eu]    = 'cover_201465eu'

    # Buyer account details
    #
    out_row[ind_buy_acct_id_type]  = 'buy_acct_id_type'
    out_row[ind_buy_acct_np_code]  = 'buy_acct_np_code'
    out_row[ind_buy_acct_id_code]  = 'buy_acct_id_code'
    out_row[ind_buy_acct_country]  = 'buy_acct_country'
    out_row[ind_buy_acct_forename] = 'buy_acct_forename'
    out_row[ind_buy_acct_surname]  = 'buy_acct_surname'
    out_row[ind_buy_acct_birthdt]  = 'buy_acct_birthdt'

    # Buyer Decision Maker details
    #
    out_row[ind_buy_dcsn_id_type]  = 'buy_dcsn_id_type'
    out_row[ind_buy_dcsn_np_code]  = 'buy_dcsn_np_code'
    out_row[ind_buy_dcsn_id_code]  = 'buy_dcsn_id_code'
    out_row[ind_buy_dcsn_forename] = 'buy_dcsn_forename'
    out_row[ind_buy_dcsn_surname]  = 'buy_dcsn_surname'
    out_row[ind_buy_dcsn_birthdt]  = 'buy_dcsn_birthdt'

    # Seller account details
    #
    out_row[ind_sel_acct_id_type]  = 'sel_acct_id_type'
    out_row[ind_sel_acct_np_code]  = 'sel_acct_np_code'
    out_row[ind_sel_acct_id_code]  = 'sel_acct_id_code'
    out_row[ind_sel_acct_country]  = 'sel_acct_country'
    out_row[ind_sel_acct_forename] = 'sel_acct_forename'
    out_row[ind_sel_acct_surname]  = 'sel_acct_surname'
    out_row[ind_sel_acct_birthdt]  = 'sel_acct_birthdt'

    # Seller Decision Maker details
    #
    out_row[ind_sel_dcsn_id_type]  = 'sel_dcsn_id_type'
    out_row[ind_sel_dcsn_np_code]  = 'sel_dcsn_np_code'
    out_row[ind_sel_dcsn_id_code]  = 'sel_dcsn_id_code'
    out_row[ind_sel_dcsn_forename] = 'sel_dcsn_forename'
    out_row[ind_sel_dcsn_surname]  = 'sel_dcsn_surname'
    out_row[ind_sel_dcsn_birthdt]  = 'sel_dcsn_birthdt'

    # Transmission details
    #
    out_row[ind_trnsm_order_ind]   = 'trnsm_order_ind'
    out_row[ind_trnsm_buy_id_code] = 'trnsm_buy_id_code'
    out_row[ind_trnsm_sel_id_code] = 'trnsm_sel_id_code'

    # Transaction details
    #
    out_row[ind_trnsc_datetime]    = 'trnsc_datetime'
    out_row[ind_trnsc_trade_cap]   = 'trnsc_trade_cap'
    out_row[ind_trnsc_qty_type]    = 'trnsc_qty_type'
    out_row[ind_trnsc_qty_val]     = 'trnsc_qty_val'
    out_row[ind_trnsc_qty_ccy]     = 'trnsc_qty_ccy'
    out_row[ind_trnsc_drv_notion]  = 'trnsc_drv_notion'
    out_row[ind_trnsc_prc_type]    = 'trnsc_prc_type'
    out_row[ind_trnsc_prc_val]     = 'trnsc_prc_val'
    out_row[ind_trnsc_prc_ccy]     = 'trnsc_prc_ccy'
    out_row[ind_trnsc_net_amt]     = 'trnsc_net_amt'
    out_row[ind_trnsc_venue]       = 'trnsc_venue'
    out_row[ind_trnsc_brnch_ctry]  = 'trnsc_brnch_ctry'
    out_row[ind_trnsc_up_fr_amt]   = 'trnsc_up_fr_amt'
    out_row[ind_trnsc_up_fr_ccy]   = 'trnsc_up_fr_ccy'
    out_row[ind_trnsc_cmpnt_id]    = 'trnsc_cmpnt_id'

    # Instrument details
    #
    out_row[ind_instr_id_code]     = 'instr_id_code'
    out_row[ind_instr_full_name]   = 'instr_full_name'
    out_row[ind_instr_class]       = 'instr_class'
    out_row[ind_instr_notnl_ccy1]  = 'instr_notnl_ccy1'
    out_row[ind_instr_notnl_ccy2]  = 'instr_notnl_ccy2'
    out_row[ind_instr_price_mult]  = 'instr_price_mult'
    out_row[ind_instr_under_code]  = 'instr_under_code'
    out_row[ind_instr_under_name]  = 'instr_under_name'
    out_row[ind_instr_under_term]  = 'instr_under_term'
    out_row[ind_instr_optn_type]   = 'instr_optn_type'
    out_row[ind_instr_strk_type]   = 'instr_strk_type'
    out_row[ind_instr_strk_price]  = 'instr_strk_price'
    out_row[ind_instr_strk_ccy]    = 'instr_strk_ccy'
    out_row[ind_instr_optn_exrc]   = 'instr_optn_exrc'
    out_row[ind_instr_mat_date]    = 'instr_mat_date'
    out_row[ind_instr_exp_date]    = 'instr_exp_date'
    out_row[ind_instr_dlvry_type]  = 'instr_dlvry_type'

    # Trading details
    #
    out_row[ind_trade_invst_type]  = 'trade_invst_type'
    out_row[ind_trade_invst_np]    = 'trade_invst_np'
    out_row[ind_trade_invst_code]  = 'trade_invst_code'
    out_row[ind_trade_invst_ctry]  = 'trade_invst_ctry'
    out_row[ind_trade_exec_type]   = 'trade_exec_type'
    out_row[ind_trade_exec_np]     = 'trade_exec_np'
    out_row[ind_trade_exec_code]   = 'trade_exec_code'
    out_row[ind_trade_exec_ctry]   = 'trade_exec_ctry'
    out_row[ind_trade_waiver_ind]  = 'trade_waiver_ind'
    out_row[ind_trade_shrt_ind]    = 'trade_shrt_ind'
    out_row[ind_trade_post_ind]    = 'trade_post_ind'
    out_row[ind_trade_drv_ind]     = 'trade_drv_ind'
    out_row[ind_trade_sec_ind]     = 'trade_sec_ind'

    # Eligibility details
    #
    out_row[ind_elig_branch_loc]   = 'elig_branch_loc'
    out_row[ind_elig_trnsc_type]   = 'elig_trnsc_type'
    out_row[ind_elig_cycle_event]  = 'elig_cycle_event'


# For all new transactions
def get_output_row_new(xml_tx_new, xml_file):

    global client_modes

    # Report Details
    out_row[ind_report_status]  = 'NEWT'
    out_row[ind_trans_ref_no]   = xml_find_text(xml_tx_new, 'TxId')
    out_row[ind_entity_id_code] = xml_find_text(xml_tx_new, 'ExctgPty')

    if xml_find(xml_tx_new, 'InvstmtPtyInd') is not None:
        if xml_find_text(xml_tx_new, 'InvstmtPtyInd') == '1':
            out_row[ind_cover_201465eu] = 'true'
        elif xml_find_text(xml_tx_new, 'InvstmtPtyInd') == '0':
            out_row[ind_cover_201465eu] = 'false'
        else:
            out_row[ind_cover_201465eu] = xml_find_text(xml_tx_new, 'InvstmtPtyInd')

    # ----------------------------- Buyer details ---------------------------
    list_buy_acct_id_type  = []
    list_buy_acct_np_code  = []
    list_buy_acct_id_code  = []
    list_buy_acct_country  = []
    list_buy_acct_forename = []
    list_buy_acct_surname  = []
    list_buy_acct_birthdt  = []

    list_buy_dcsn_id_type  = []
    list_buy_dcsn_np_code  = []
    list_buy_dcsn_id_code  = []
    list_buy_dcsn_forename = []
    list_buy_dcsn_surname  = []
    list_buy_dcsn_birthdt  = []

    xml_tx_new_buy = xml_find(xml_tx_new, 'Buyr')

    if xml_tx_new_buy is not None:
        xml_tx_new_buy_accts = xml_findall(xml_tx_new_buy, 'AcctOwnr')
        if xml_tx_new_buy_accts is not None:
            for xml_tx_new_buy_acct in xml_tx_new_buy_accts:

                single_id_type  = ''
                single_id_code  = ''
                single_forename = ''
                single_surname  = ''
                single_birthdt  = ''

# ----------------------------- Buyer Id Code Type
                xml_tx_new_buy_acct_id = xml_find(xml_tx_new_buy_acct, 'Id')

                if xml_tx_new_buy_acct_id is not None:
                    xml_tx_new_buy_acct_id_prsn = xml_find(xml_tx_new_buy_acct_id, 'Prsn')

                    if xml_find(xml_tx_new_buy_acct_id, 'LEI') is not None:
                        single_id_type = 'LEI'

                    elif xml_find(xml_tx_new_buy_acct_id, 'MIC') is not None:
                        single_id_type = 'MIC'

                    elif xml_tx_new_buy_acct_id_prsn is not None:
                        xml_tx_new_buy_acct_id_prsn_othr = xml_find(xml_tx_new_buy_acct_id_prsn, 'Othr')
                        if xml_tx_new_buy_acct_id_prsn_othr is not None:
                            xml_tx_new_buy_acct_id_prsn_othr_schmenm = xml_find(xml_tx_new_buy_acct_id_prsn_othr, 'SchmeNm')
                            if xml_tx_new_buy_acct_id_prsn_othr_schmenm is not None:
                                if xml_find(xml_tx_new_buy_acct_id_prsn_othr_schmenm, 'Cd') is not None:
                                    if xml_find_text(xml_tx_new_buy_acct_id_prsn_othr_schmenm, 'Cd') != 'NIDN':
                                        single_id_type = xml_find_text(xml_tx_new_buy_acct_id_prsn_othr_schmenm, 'Cd')
                                    else:
                                        single_id_type = 'NIND'

                                elif xml_find(xml_tx_new_buy_acct_id_prsn_othr_schmenm, 'Prty') is not None:
                                    single_id_type = xml_find_text(xml_tx_new_buy_acct_id_prsn_othr_schmenm, 'Prty')

                    else:
                        single_id_type = xml_find_text(xml_tx_new_buy_acct_id, 'Intl')
# ----------------------------------------------------------------------------------------

# --------------------------------- Buyer Id Code
                    if xml_find(xml_tx_new_buy_acct_id, 'LEI') is not None:
                        single_id_code = xml_find_text(xml_tx_new_buy_acct_id, 'LEI')

                    elif xml_find(xml_tx_new_buy_acct_id, 'MIC') is not None:
                        single_id_code = xml_find_text(xml_tx_new_buy_acct_id, 'MIC')

                    elif xml_tx_new_buy_acct_id_prsn is not None:
                        xml_tx_new_buy_acct_id_prsn_othr = xml_find(xml_tx_new_buy_acct_id_prsn, 'Othr')
                        if xml_tx_new_buy_acct_id_prsn_othr is not None:
                            xml_tx_new_buy_acct_id_prsn_othr_id = xml_find(xml_tx_new_buy_acct_id_prsn_othr, 'Id')
                            if xml_tx_new_buy_acct_id_prsn_othr_id is not None:
                                single_id_code = xml_find_text(xml_tx_new_buy_acct_id_prsn_othr, 'Id')

                    else:
                        single_id_code = xml_find_text(xml_tx_new_buy_acct_id, 'Intl')
# ----------------------------------------------------------------------------------------

# --------------------------------- First, last, DOB Codes
                    if xml_find(xml_tx_new_buy_acct_id, 'Prsn') is not None:
                        xml_tx_new_buy_acct_id_prsn = xml_find(xml_tx_new_buy_acct_id, 'Prsn')
                        if xml_find(xml_tx_new_buy_acct_id_prsn, 'FrstNm') is not None:
                            single_forename = xml_find_text(xml_tx_new_buy_acct_id_prsn, 'FrstNm')
                        if xml_find(xml_tx_new_buy_acct_id_prsn, 'Nm') is not None:
                            single_surname = xml_find_text(xml_tx_new_buy_acct_id_prsn, 'Nm')
                        if xml_find(xml_tx_new_buy_acct_id_prsn, 'BirthDt') is not None:
                            single_birthdt = xml_find_text(xml_tx_new_buy_acct_id_prsn, 'BirthDt')
# ----------------------------------------------------------------------------------------

                list_buy_acct_id_type.append(single_id_type)
                list_buy_acct_np_code.append('')
                list_buy_acct_id_code.append(single_id_code)
                list_buy_acct_country.append(xml_find_text(xml_tx_new_buy_acct, 'CtryOfBrnch'))
                list_buy_acct_forename.append(single_forename)
                list_buy_acct_surname.append(single_surname)
                list_buy_acct_birthdt.append(single_birthdt)

        xml_tx_new_buy_dcsns = xml_findall(xml_tx_new_buy, 'DcsnMakr')
        if xml_tx_new_buy_dcsns is not None:
            for xml_tx_new_buy_dcsn in xml_tx_new_buy_dcsns:

                single_id_type  = ''
                single_id_code  = ''
                single_forename = ''
                single_surname  = ''
                single_birthdt  = ''

# --------------------------------- Buyer Decision Maker Code Type
                if xml_tx_new_buy_dcsn is not None:
                    if xml_find(xml_tx_new_buy_dcsn, 'LEI') is not None:
                        single_id_type = 'LEI'

                    elif xml_find(xml_tx_new_buy_dcsn, 'Prsn') is not None:
                        xml_tx_new_buy_dcsn_prsn = xml_find(xml_tx_new_buy_dcsn, 'Prsn')
                        if xml_tx_new_buy_dcsn_prsn is not None:
                            xml_tx_new_buy_dcsn_prsn_othr = xml_find(xml_tx_new_buy_dcsn_prsn, 'Othr')
                            if xml_tx_new_buy_dcsn_prsn_othr is not None:
                                xml_tx_new_buy_dcsn_prsn_othr_schmenm = xml_find(xml_tx_new_buy_dcsn_prsn_othr, 'SchmeNm')
                                if xml_tx_new_buy_dcsn_prsn_othr_schmenm is not None:
                                    if xml_find(xml_tx_new_buy_dcsn_prsn_othr_schmenm, 'Cd') is not None:
                                        if xml_find_text(xml_tx_new_buy_dcsn_prsn_othr_schmenm, 'Cd') != 'NIDN':
                                            single_id_type = xml_find_text(xml_tx_new_buy_dcsn_prsn_othr_schmenm, 'Cd')
                                        else:
                                            single_id_type = 'NIND'

                                    elif xml_find(xml_tx_new_buy_dcsn_prsn_othr_schmenm, 'Prty') is not None:
                                        single_id_type = xml_find_text(xml_tx_new_buy_dcsn_prsn_othr_schmenm, 'Prty')
# ----------------------------------------------------------------------------------------

# --------------------------------- Buyer Decision Maker ID Code
                    if xml_find(xml_tx_new_buy_dcsn, 'LEI') is not None:
                        single_id_code = xml_find_text(xml_tx_new_buy_dcsn, 'LEI')

                    elif xml_find(xml_tx_new_buy_dcsn, 'Prsn') is not None:
                        xml_tx_new_buy_dcsn_prsn = xml_find(xml_tx_new_buy_dcsn, 'Prsn')
                        if xml_tx_new_buy_dcsn_prsn is not None:
                            xml_tx_new_buy_dcsn_prsn_othr = xml_find(xml_tx_new_buy_dcsn_prsn, 'Othr')
                            if xml_tx_new_buy_dcsn_prsn_othr is not None:
                                single_id_code = xml_find_text(xml_tx_new_buy_dcsn_prsn_othr, 'Id')
# ----------------------------------------------------------------------------------------

# ------------------------------------ First, last, DOB Codes
                    if xml_find(xml_tx_new_buy_dcsn, 'Prsn') is not None:
                        xml_tx_new_buy_dcsn_prsn = xml_find(xml_tx_new_buy_dcsn, 'Prsn')
                        single_forename = xml_find_text(xml_tx_new_buy_dcsn_prsn, 'FrstNm')
                        single_surname  = xml_find_text(xml_tx_new_buy_dcsn_prsn, 'Nm')
                        single_birthdt  = xml_find_text(xml_tx_new_buy_dcsn_prsn, 'BirthDt')
# ----------------------------------------------------------------------------------------

                list_buy_dcsn_id_type.append(single_id_type)
                list_buy_dcsn_np_code.append('')
                list_buy_dcsn_id_code.append(single_id_code)
                list_buy_dcsn_forename.append(single_forename)
                list_buy_dcsn_surname.append(single_surname)
                list_buy_dcsn_birthdt.append(single_birthdt)

    out_row[ind_buy_acct_id_type]  = delim.join(list_buy_acct_id_type)
    out_row[ind_buy_acct_np_code]  = delim.join(list_buy_acct_np_code)
    out_row[ind_buy_acct_id_code]  = delim.join(list_buy_acct_id_code)
    out_row[ind_buy_acct_country]  = delim.join(list_buy_acct_country)
    out_row[ind_buy_acct_forename] = delim.join(list_buy_acct_forename)
    out_row[ind_buy_acct_surname]  = delim.join(list_buy_acct_surname)
    out_row[ind_buy_acct_birthdt]  = delim.join(list_buy_acct_birthdt)

    out_row[ind_buy_dcsn_id_type]  = delim.join(list_buy_dcsn_id_type)
    out_row[ind_buy_dcsn_np_code]  = delim.join(list_buy_dcsn_np_code)
    out_row[ind_buy_dcsn_id_code]  = delim.join(list_buy_dcsn_id_code)
    out_row[ind_buy_dcsn_forename] = delim.join(list_buy_dcsn_forename)
    out_row[ind_buy_dcsn_surname]  = delim.join(list_buy_dcsn_surname)
    out_row[ind_buy_dcsn_birthdt]  = delim.join(list_buy_dcsn_birthdt)

    # ----------------------------- Seller details ---------------------------
    list_sel_acct_id_type  = []
    list_sel_acct_np_code  = []
    list_sel_acct_id_code  = []
    list_sel_acct_country  = []
    list_sel_acct_forename = []
    list_sel_acct_surname  = []
    list_sel_acct_birthdt  = []

    list_sel_dcsn_id_type  = []
    list_sel_dcsn_np_code  = []
    list_sel_dcsn_id_code  = []
    list_sel_dcsn_forename = []
    list_sel_dcsn_surname  = []
    list_sel_dcsn_birthdt  = []

    xml_tx_new_sel = xml_find(xml_tx_new, 'Sellr')
    if xml_tx_new_sel is not None:
        # --- Seller Id ---
        xml_tx_new_sel_accts = xml_findall(xml_tx_new_sel, 'AcctOwnr')
        if xml_tx_new_sel_accts is not None:
            for xml_tx_new_sel_acct in xml_tx_new_sel_accts:

                single_id_type  = ''
                single_id_code  = ''
                single_forename = ''
                single_surname  = ''
                single_birthdt  = ''

                xml_tx_new_sel_acct_id = xml_find(xml_tx_new_sel_acct, 'Id')

# ----------------------------- Seller Id Code Type
                if xml_tx_new_sel_acct_id is not None:
                    xml_tx_new_sel_acct_id_prsn = xml_find(xml_tx_new_sel_acct_id, 'Prsn')

                    if xml_find(xml_tx_new_sel_acct_id, 'LEI') is not None:
                        single_id_type = 'LEI'

                    elif xml_find(xml_tx_new_sel_acct_id, 'MIC') is not None:
                        single_id_type = 'MIC'

                    elif xml_tx_new_sel_acct_id_prsn is not None:
                        xml_tx_new_sel_acct_id_prsn_othr = xml_find(xml_tx_new_sel_acct_id_prsn, 'Othr')
                        if xml_tx_new_sel_acct_id_prsn_othr is not None:
                            xml_tx_new_sel_acct_id_prsn_othr_schmenm = xml_find(xml_tx_new_sel_acct_id_prsn_othr, 'SchmeNm')
                            if xml_tx_new_sel_acct_id_prsn_othr_schmenm is not None:
                                if xml_find(xml_tx_new_sel_acct_id_prsn_othr_schmenm, 'Cd') is not None:
                                    if xml_find_text(xml_tx_new_sel_acct_id_prsn_othr_schmenm, 'Cd') != 'NIDN':
                                        single_id_type = xml_find_text(xml_tx_new_sel_acct_id_prsn_othr_schmenm, 'Cd')
                                    else:
                                        single_id_type = 'NIND'

                                elif xml_find(xml_tx_new_sel_acct_id_prsn_othr_schmenm, 'Prty') is not None:
                                    single_id_type = xml_find_text(xml_tx_new_sel_acct_id_prsn_othr_schmenm, 'Prty')

                    else:
                        single_id_type = xml_find_text(xml_tx_new_sel_acct_id, 'Intl')
# ----------------------------------------------------------------------------------------

# ----------------------------- Seller Id Code
                    if xml_find(xml_tx_new_sel_acct_id, 'LEI') is not None:
                        single_id_code = xml_find_text(xml_tx_new_sel_acct_id, 'LEI')

                    elif xml_find(xml_tx_new_sel_acct_id, 'MIC') is not None:
                        single_id_code = xml_find_text(xml_tx_new_sel_acct_id, 'MIC')

                    elif xml_tx_new_sel_acct_id_prsn is not None:
                        xml_tx_new_sel_acct_id_prsn_othr = xml_find(xml_tx_new_sel_acct_id_prsn, 'Othr')
                        if xml_tx_new_sel_acct_id_prsn_othr is not None:
                            if xml_find(xml_tx_new_sel_acct_id_prsn_othr, 'Id') is not None:
                                single_id_code = xml_find_text(xml_tx_new_sel_acct_id_prsn_othr, 'Id')

                    else:
                        single_id_code = xml_find_text(xml_tx_new_sel_acct_id, 'Intl')
# ----------------------------------------------------------------------------------------

# ------------------------------------ First, last, DOB Codes
                    if xml_find(xml_tx_new_sel_acct_id, 'Prsn') is not None:
                        xml_tx_new_sel_acct_id_prsn = xml_find(xml_tx_new_sel_acct_id, 'Prsn')
                        single_forename = xml_find_text(xml_tx_new_sel_acct_id_prsn, 'FrstNm')
                        single_surname  = xml_find_text(xml_tx_new_sel_acct_id_prsn, 'Nm')
                        single_birthdt  = xml_find_text(xml_tx_new_sel_acct_id_prsn, 'BirthDt')
# ----------------------------------------------------------------------------------------

                list_sel_acct_id_type.append(single_id_type)
                list_sel_acct_np_code.append('')
                list_sel_acct_id_code.append(single_id_code)
                list_sel_acct_country.append(xml_find_text(xml_tx_new_sel_acct, 'CtryOfBrnch'))
                list_sel_acct_forename.append(single_forename)
                list_sel_acct_surname.append(single_surname)
                list_sel_acct_birthdt.append(single_birthdt)

        # --- Seller Decision Maker ---
        xml_tx_new_sel_dcsns = xml_findall(xml_tx_new_sel, 'DcsnMakr')
        if xml_tx_new_sel_dcsns is not None:
            for xml_tx_new_sel_dcsn in xml_tx_new_sel_dcsns:

                single_id_type  = ''
                single_id_code  = ''
                single_forename = ''
                single_surname  = ''
                single_birthdt  = ''

                if xml_tx_new_sel_dcsn is not None:

# ----------------------------- Seller Decision Code Type
                    if xml_find(xml_tx_new_sel_dcsn, 'LEI') is not None:
                        single_id_type = 'LEI'

                    elif xml_find(xml_tx_new_sel_dcsn, 'Prsn') is not None:
                        xml_tx_new_sel_dcsn_prsn = xml_find(xml_tx_new_sel_dcsn, 'Prsn')
                        if xml_tx_new_sel_dcsn_prsn is not None:
                            xml_tx_new_sel_dcsn_prsn_othr = xml_find(xml_tx_new_sel_dcsn_prsn, 'Othr')
                            if xml_tx_new_sel_dcsn_prsn_othr is not None:
                                xml_tx_new_sel_dcsn_prsn_othr_schmenm = xml_find(xml_tx_new_sel_dcsn_prsn_othr, 'SchmeNm')
                                if xml_tx_new_sel_dcsn_prsn_othr_schmenm is not None:
                                    if xml_find(xml_tx_new_sel_dcsn_prsn_othr_schmenm, 'Cd') is not None:
                                        if xml_find_text(xml_tx_new_sel_dcsn_prsn_othr_schmenm, 'Cd') != 'NIDN':
                                            single_id_type = xml_find_text(xml_tx_new_sel_dcsn_prsn_othr_schmenm, 'Cd')
                                        else:
                                            single_id_type = 'NIND'

                                    elif xml_find(xml_tx_new_sel_dcsn_prsn_othr_schmenm, 'Prty') is not None:
                                        single_id_type = xml_find_text(xml_tx_new_sel_dcsn_prsn_othr_schmenm, 'Prty')
# ----------------------------------------------------------------------------------------

# ----------------------------- Seller Decision Id Code
                    if xml_find(xml_tx_new_sel_dcsn, 'LEI') is not None:
                        single_id_code = xml_find_text(xml_tx_new_sel_dcsn, 'LEI')

                    elif xml_find(xml_tx_new_sel_dcsn, 'Prsn') is not None:
                        xml_tx_new_sel_dcsn_prsn = xml_find(xml_tx_new_sel_dcsn, 'Prsn')
                        if xml_tx_new_sel_dcsn_prsn is not None:
                            xml_tx_new_sel_dcsn_prsn_othr = xml_find(xml_tx_new_sel_dcsn_prsn, 'Othr')
                            if xml_tx_new_sel_dcsn_prsn_othr is not None:
                                if xml_find(xml_tx_new_sel_dcsn_prsn_othr, 'Id') is not None:
                                    single_id_code = xml_find_text(xml_tx_new_sel_dcsn_prsn_othr, 'Id')
# ----------------------------------------------------------------------------------------

                    if xml_find(xml_tx_new_sel_dcsn, 'Prsn') is not None:
                        xml_tx_new_sel_dcsn_prsn = xml_find(xml_tx_new_sel_dcsn, 'Prsn')
                        single_forename = xml_find_text(xml_tx_new_sel_dcsn_prsn, 'FrstNm')
                        single_surname = xml_find_text(xml_tx_new_sel_dcsn_prsn, 'Nm')
                        single_birthdt = xml_find_text(xml_tx_new_sel_dcsn_prsn, 'BirthDt')

                list_sel_dcsn_id_type.append(single_id_type)
                list_sel_dcsn_np_code.append('')
                list_sel_dcsn_id_code.append(single_id_code)
                list_sel_dcsn_forename.append(single_forename)
                list_sel_dcsn_surname.append(single_surname)
                list_sel_dcsn_birthdt.append(single_birthdt)

    # output Seller Id & Seller Decision Maker values to columns for row
    out_row[ind_sel_acct_id_type]  = delim.join(list_sel_acct_id_type)
    out_row[ind_sel_acct_np_code]  = delim.join(list_sel_acct_np_code)
    out_row[ind_sel_acct_id_code]  = delim.join(list_sel_acct_id_code)
    out_row[ind_sel_acct_country]  = delim.join(list_sel_acct_country)
    out_row[ind_sel_acct_forename] = delim.join(list_sel_acct_forename)
    out_row[ind_sel_acct_surname]  = delim.join(list_sel_acct_surname)
    out_row[ind_sel_acct_birthdt]  = delim.join(list_sel_acct_birthdt)

    out_row[ind_sel_dcsn_id_type]  = delim.join(list_sel_dcsn_id_type)
    out_row[ind_sel_dcsn_np_code]  = delim.join(list_sel_dcsn_np_code)
    out_row[ind_sel_dcsn_id_code]  = delim.join(list_sel_dcsn_id_code)
    out_row[ind_sel_dcsn_forename] = delim.join(list_sel_dcsn_forename)
    out_row[ind_sel_dcsn_surname]  = delim.join(list_sel_dcsn_surname)
    out_row[ind_sel_dcsn_birthdt]  = delim.join(list_sel_dcsn_birthdt)

# ----------------------------- Transmission details ---------------------------
    single_trnsm_order_ind   = ''
    single_trnsm_buy_id_code = ''
    single_trnsm_sel_id_code = ''

    xml_tx_new_trnsm = xml_find(xml_tx_new, 'OrdrTrnsmssn')
    if xml_tx_new_trnsm is not None:
        single_trnsm_order_ind = xml_find_text(xml_tx_new_trnsm, 'TrnsmssnInd')
        if single_trnsm_order_ind == '1':
            single_trnsm_order_ind = 'True'
        elif single_trnsm_order_ind == '0':
            single_trnsm_order_ind = 'False'

        single_trnsm_buy_id_code = xml_find_text(xml_tx_new_trnsm, 'TrnsmttgBuyr')
        single_trnsm_sel_id_code = xml_find_text(xml_tx_new_trnsm, 'TrnsmttgSellr')

    out_row[ind_trnsm_order_ind]   = single_trnsm_order_ind
    out_row[ind_trnsm_buy_id_code] = single_trnsm_buy_id_code
    out_row[ind_trnsm_sel_id_code] = single_trnsm_sel_id_code

# ----------------------------- Transaction details ---------------------------
    single_trnsc_datetime    = ''
    single_trnsc_trade_cap   = ''
    single_trnsc_qty_type    = ''
    single_trnsc_qty_val     = ''
    single_trnsc_qty_ccy     = ''
    single_trnsc_drv_notion  = ''
    single_trnsc_prc_type    = ''
    single_trnsc_prc_val     = ''
    single_trnsc_prc_ccy     = ''
    single_trnsc_net_amt     = ''
    single_trnsc_venue       = ''
    single_trnsc_brnch_ctry  = ''
    single_trnsc_up_fr_amt   = ''
    single_trnsc_up_fr_ccy   = ''
    single_trnsc_cmpnt_id    = ''

    xml_tx_new_trnsc = xml_find(xml_tx_new, 'Tx')
    if xml_tx_new_trnsc is not None:

# ----------------------------- Trading Date Time & Capacity
        single_trnsc_datetime    = xml_find_text(xml_tx_new_trnsc, 'TradDt')
        single_trnsc_trade_cap   = xml_find_text(xml_tx_new_trnsc, 'TradgCpcty')
# ----------------------------------------------------------------------------------------

# ----------------------------- Quantity - Type, Quantity & Quantity Currency
        xml_tx_new_trnsc_qty = xml_find(xml_tx_new_trnsc, 'Qty')
        if xml_tx_new_trnsc_qty is not None:
            if xml_find(xml_tx_new_trnsc_qty, 'Unit') is not None:
                single_trnsc_qty_type = 'UNIT'
                single_trnsc_qty_val = xml_find_text(xml_tx_new_trnsc_qty, 'Unit')
            elif xml_find(xml_tx_new_trnsc_qty, 'NmnlVal') is not None:
                single_trnsc_qty_type = 'NOMI'
                single_trnsc_qty_val = xml_find_text(xml_tx_new_trnsc_qty, 'NmnlVal')
                xml_tx_new_trnsc_qty_nmval = xml_find(xml_tx_new_trnsc_qty, 'NmnlVal')
                single_trnsc_qty_ccy = xml_get(xml_tx_new_trnsc_qty_nmval, 'Amt', 'Ccy')
            elif xml_find(xml_tx_new_trnsc_qty, 'MntryVal') is not None:
                single_trnsc_qty_type = 'MONE'
                single_trnsc_qty_val = xml_find_text(xml_tx_new_trnsc_qty, 'MntryVal')
                xml_tx_new_trnsc_qty_mntryval = xml_find(xml_tx_new_trnsc_qty, 'MntryVal')
                single_trnsc_qty_ccy = xml_get(xml_tx_new_trnsc_qty_mntryval, 'Amt', 'Ccy')
# ----------------------------------------------------------------------------------------

# ----------------------------- Derivative Notional
        single_trnsc_drv_notion = xml_find_text(xml_tx_new_trnsc, 'DerivNtnlChng')
# ----------------------------------------------------------------------------------------

# ----------------------------- Price - Type
        xml_tx_new_trnsc_pric = xml_find(xml_tx_new_trnsc, 'Pric')
        if xml_tx_new_trnsc_pric is not None:
            xml_tx_new_trnsc_pric_pric = xml_find(xml_tx_new_trnsc_pric, 'Pric')
            xml_tx_new_trnsc_pric_nopric = xml_find(xml_tx_new_trnsc_pric, 'NoPric')

            if xml_tx_new_trnsc_pric_pric is not None:
                if xml_find(xml_tx_new_trnsc_pric_pric, 'MntryVal') is not None:
                    single_trnsc_prc_type = 'MONE'

                elif xml_find(xml_tx_new_trnsc_pric_pric, 'Pctg') is not None:
                    single_trnsc_prc_type = 'PERC'

                elif xml_find(xml_tx_new_trnsc_pric_pric, 'Yld') is not None:
                    single_trnsc_prc_type = 'YIEL'

                elif xml_find(xml_tx_new_trnsc_pric_pric, 'BsisPts') is not None:
                    single_trnsc_prc_type = 'BPNT'

            elif xml_tx_new_trnsc_pric_nopric is not None:
                if xml_find(xml_tx_new_trnsc_pric_nopric, 'Pdg') is not None:
                    single_trnsc_prc_type = xml_find_text(xml_tx_new_trnsc_pric_nopric, 'Pdg')
# ----------------------------------------------------------------------------------------

# ----------------------------- Price
            if xml_tx_new_trnsc_pric_pric is not None:
                xml_tx_new_trnsc_pric_pric_mntryval = xml_find(xml_tx_new_trnsc_pric_pric, 'MntryVal')
                if xml_tx_new_trnsc_pric_pric_mntryval is not None:
                    if xml_find_text(xml_tx_new_trnsc_pric_pric_mntryval, 'Sgn') in ('1', 'true'):
                        single_trnsc_prc_val = float('-' + str(xml_find_text(xml_tx_new_trnsc_pric_pric_mntryval, 'Amt')))
                    else:
                        single_trnsc_prc_val = xml_find_text(xml_tx_new_trnsc_pric_pric_mntryval, 'Amt')

                elif xml_find(xml_tx_new_trnsc_pric_pric, 'Pctg') is not None:
                    single_trnsc_prc_val = xml_find_text(xml_tx_new_trnsc_pric_pric, 'Pctg')

                elif xml_find(xml_tx_new_trnsc_pric_pric, 'Yld') is not None:
                    single_trnsc_prc_val = xml_find_text(xml_tx_new_trnsc_pric_pric, 'Yld')

                elif xml_find(xml_tx_new_trnsc_pric_pric, 'BsisPts') is not None:
                    single_trnsc_prc_val = xml_find_text(xml_tx_new_trnsc_pric_pric, 'BsisPts')

            elif xml_tx_new_trnsc_pric_nopric is not None:
                if xml_find(xml_tx_new_trnsc_pric_nopric, 'Pdg') is not None:
                    if xml_find_text(xml_tx_new_trnsc_pric_nopric, 'Pdg') == 'PNDG':
                        single_trnsc_prc_val = xml_find_text(xml_tx_new_trnsc_pric_nopric, 'Pdg')
# ----------------------------------------------------------------------------------------

# ----------------------------- Price Currency
            if xml_tx_new_trnsc_pric_pric is not None:
                xml_tx_new_trnsc_pric_pric_mntryval = xml_find(xml_tx_new_trnsc_pric_pric, 'MntryVal')
                if xml_tx_new_trnsc_pric_pric_mntryval is not None:
                    single_trnsc_prc_ccy = xml_get(xml_tx_new_trnsc_pric_pric, 'MntryVal', 'Ccy')
            elif xml_tx_new_trnsc_pric_nopric is not None:
                single_trnsc_prc_ccy = xml_find_text(xml_tx_new_trnsc_pric_nopric, 'Ccy')
# ----------------------------------------------------------------------------------------

# ----------------------------- Net Amount, Venue & Country of Branch
        single_trnsc_net_amt = xml_find_text(xml_tx_new_trnsc, 'NetAmt')
        single_trnsc_venue = xml_find_text(xml_tx_new_trnsc, 'TradVn')
        single_trnsc_brnch_ctry = xml_find_text(xml_tx_new_trnsc, 'CtryOfBrnch')
# ----------------------------------------------------------------------------------------

# ----------------------------- Up-front Payment & Complex Trade Id
        xml_tx_new_trnsc_upfr = xml_find(xml_tx_new_trnsc, 'UpFrntPmt')
        if xml_tx_new_trnsc_upfr is not None:
            xml_tx_new_trnsc_upfr_amt = xml_find_text(xml_tx_new_trnsc_upfr, 'Amt')

            if xml_tx_new_trnsc_upfr_amt:
                xml_tx_new_trnsc_upfr_sgn = xml_find_text(xml_tx_new_trnsc_upfr, 'Sgn')
                single_trnsc_up_fr_ccy = xml_get(xml_tx_new_trnsc_upfr, 'Amt', 'Ccy')

                if xml_tx_new_trnsc_upfr_sgn in ('1', 'true'):
                    single_trnsc_up_fr_amt = '-' + str(xml_tx_new_trnsc_upfr_amt)
                else:
                    single_trnsc_up_fr_amt = xml_tx_new_trnsc_upfr_amt

        single_trnsc_cmpnt_id = xml_find_text(xml_tx_new_trnsc, 'CmplxTradCmpntId')
# ----------------------------------------------------------------------------------------

    out_row[ind_trnsc_datetime]    = single_trnsc_datetime
    out_row[ind_trnsc_trade_cap]   = single_trnsc_trade_cap
    out_row[ind_trnsc_qty_type]    = single_trnsc_qty_type
    out_row[ind_trnsc_qty_val]     = single_trnsc_qty_val
    out_row[ind_trnsc_qty_ccy]     = single_trnsc_qty_ccy
    out_row[ind_trnsc_drv_notion]  = single_trnsc_drv_notion
    out_row[ind_trnsc_prc_type]    = single_trnsc_prc_type
    out_row[ind_trnsc_prc_val]     = single_trnsc_prc_val
    out_row[ind_trnsc_prc_ccy]     = single_trnsc_prc_ccy
    out_row[ind_trnsc_net_amt]     = single_trnsc_net_amt
    out_row[ind_trnsc_venue]       = single_trnsc_venue
    out_row[ind_trnsc_brnch_ctry]  = single_trnsc_brnch_ctry
    out_row[ind_trnsc_up_fr_amt]   = single_trnsc_up_fr_amt
    out_row[ind_trnsc_up_fr_ccy]   = single_trnsc_up_fr_ccy
    out_row[ind_trnsc_cmpnt_id]    = single_trnsc_cmpnt_id


# ----------------------------- Instrument details ---------------------------
    single_instr_id_code     = ''
    single_instr_full_name   = ''
    single_instr_class       = ''
    single_instr_notnl_ccy1  = ''
    single_instr_notnl_ccy2  = ''
    single_instr_price_mult  = ''
    list_instr_under_code    = []
    single_instr_under_name  = ''
    single_instr_under_term  = ''
    single_instr_optn_type   = ''
    single_instr_strk_type   = ''
    single_instr_strk_price  = ''
    single_instr_strk_ccy    = ''
    single_instr_optn_exrc   = ''
    single_instr_mat_date    = ''
    single_instr_exp_date    = ''
    single_instr_dlvry_type  = ''

    xml_tx_new_instr = xml_find(xml_tx_new, 'FinInstrm')
    if xml_tx_new_instr is not None:

# ------------------------------------ Instrument identification code
        xml_tx_new_instr_othr = xml_find(xml_tx_new_instr, 'Othr')
        if xml_find(xml_tx_new_instr, 'Id') is not None:
            single_instr_id_code = xml_find_text(xml_tx_new_instr, 'Id')

        elif xml_tx_new_instr_othr is not None:
            xml_tx_new_instr_othr_fininstr = xml_find(xml_tx_new_instr_othr, 'FinInstrmGnlAttrbts')
            if xml_tx_new_instr_othr_fininstr is not None:
                if xml_find(xml_tx_new_instr_othr_fininstr, 'Id') is not None:
                    single_instr_id_code = xml_find_text(xml_tx_new_instr_othr_fininstr, 'Id')
# -------------------------------------------------------------------

# ------------------------------------ Instrument name, instrument classification, notional currency 1
                single_instr_full_name = xml_find_text(xml_tx_new_instr_othr_fininstr, 'FullNm')
                single_instr_class = xml_find_text(xml_tx_new_instr_othr_fininstr, 'ClssfctnTp')
                single_instr_notnl_ccy1 = xml_find_text(xml_tx_new_instr_othr_fininstr, 'NtnlCcy')
# ----------------------------------------------------------------------------------------

# ------------------------------------ Option Type, Strike Price - Type, Strike Price, Strike Price Currency, Option Excercise Style
            xml_tx_new_instr_othr_derivinstr = xml_find(xml_tx_new_instr_othr, 'DerivInstrmAttrbts')
            if xml_tx_new_instr_othr_derivinstr is not None:
                xml_tx_new_instr_othr_derivinstr_undr = xml_find(xml_tx_new_instr_othr_derivinstr, 'UndrlygInstrm')
                xml_tx_new_instr_othr_derivinstr_optntp = xml_find(xml_tx_new_instr_othr_derivinstr, 'OptnTp')
                xml_tx_new_instr_othr_derivinstr_strkpric = xml_find(xml_tx_new_instr_othr_derivinstr, 'StrkPric')

                if xml_tx_new_instr_othr_derivinstr_optntp is not None:
                        single_instr_optn_type = xml_find_text(xml_tx_new_instr_othr_derivinstr, 'OptnTp')

                if xml_tx_new_instr_othr_derivinstr_strkpric is not None:
                    xml_tx_new_instr_othr_derivinstr_strkpric_pric = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric, 'Pric')
                    xml_tx_new_instr_othr_derivinstr_strkpric_nopric = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric, 'NoPric')
                    if xml_tx_new_instr_othr_derivinstr_strkpric_pric is not None:
                        xml_tx_new_instr_othr_derivinstr_strkpric_pric_mntryval = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric_pric, 'MntryVal')
                        xml_tx_new_instr_othr_derivinstr_strkpric_pric_pctg = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric_pric, 'Pctg')
                        xml_tx_new_instr_othr_derivinstr_strkpric_pric_yld = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric_pric, 'Yld')
                        xml_tx_new_instr_othr_derivinstr_strkpric_pric_bsispts = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric_pric, 'BsisPts')

                        if xml_tx_new_instr_othr_derivinstr_strkpric_pric_mntryval is not None:
                            single_instr_strk_type = 'MONE'
                            single_instr_strk_ccy = xml_get(xml_tx_new_instr_othr_derivinstr_strkpric_pric_mntryval, 'Amt', 'Ccy')
                            if xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_pric_mntryval, 'Sgn') in ('1', 'true'):
                                single_instr_strk_price = '-' + str(xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_pric_mntryval, 'Amt'))
                            else:
                                single_instr_strk_price = xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_pric_mntryval, 'Amt')

                        elif xml_tx_new_instr_othr_derivinstr_strkpric_pric_pctg is not None:
                            single_instr_strk_type = 'PERC'
                            single_instr_strk_price = xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_pric, 'Pctg')

                        elif xml_tx_new_instr_othr_derivinstr_strkpric_pric_yld is not None:
                            single_instr_strk_type = 'YIEL'
                            single_instr_strk_price = xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_pric, 'Yld')

                        elif xml_tx_new_instr_othr_derivinstr_strkpric_pric_bsispts is not None:
                            single_instr_strk_type = 'BPNT'
                            single_instr_strk_price = xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_pric, 'BsisPts')

                    elif xml_tx_new_instr_othr_derivinstr_strkpric_nopric is not None:
                        xml_tx_new_instr_othr_derivinstr_strkpric_nopric_pdg = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric_nopric, 'Pdg')
                        xml_tx_new_instr_othr_derivinstr_strkpric_nopric_ccy = xml_find(xml_tx_new_instr_othr_derivinstr_strkpric_nopric, 'Ccy')
                        if xml_tx_new_instr_othr_derivinstr_strkpric_nopric_pdg is not None:
                            single_instr_strk_type = xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_nopric, 'Pdg')
                            single_instr_strk_price = xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_nopric, 'Pdg')

                        if xml_tx_new_instr_othr_derivinstr_strkpric_nopric_ccy is not None:
                            single_instr_strk_ccy = xml_find_text(xml_tx_new_instr_othr_derivinstr_strkpric_nopric, 'Ccy')
# ----------------------------------------------------------------------------------------

# ------------------------------------ Price Multiplier
                xml_tx_new_instr_othr_derivinstr_pmltplr = xml_find(xml_tx_new_instr_othr_derivinstr, 'PricMltplr')
                if xml_tx_new_instr_othr_derivinstr_pmltplr is not None:
                    single_instr_price_mult = xml_find_text(xml_tx_new_instr_othr_derivinstr, 'PricMltplr')
# ----------------------------------------------------------------------------------------

# ------------------------------------ Notional currency 2
                xml_tx_new_instr_othr_derivinstr_asst = xml_find(xml_tx_new_instr_othr_derivinstr, 'AsstClssSpcfcAttrbts')
                if xml_tx_new_instr_othr_derivinstr_asst is not None:
                    xml_tx_new_instr_othr_derivinstr_asst_intrst = xml_find(xml_tx_new_instr_othr_derivinstr_asst, 'Intrst')
                    xml_tx_new_instr_othr_derivinstr_asst_fx = xml_find(xml_tx_new_instr_othr_derivinstr_asst, 'FX')
                    if xml_tx_new_instr_othr_derivinstr_asst_intrst is not None:
                        xml_tx_new_instr_othr_derivinstr_asst_intrst_othr = xml_find(xml_tx_new_instr_othr_derivinstr_asst_intrst, 'OthrNtnlCcy')
                        if xml_tx_new_instr_othr_derivinstr_asst_intrst_othr is not None:
                            single_instr_notnl_ccy2 = xml_find_text(xml_tx_new_instr_othr_derivinstr_asst_intrst, 'OthrNtnlCcy')

                    elif xml_tx_new_instr_othr_derivinstr_asst_fx is not None:
                        xml_tx_new_instr_othr_derivinstr_asst_fx_othr = xml_find(xml_tx_new_instr_othr_derivinstr_asst_fx, 'OthrNtnlCcy')
                        if xml_tx_new_instr_othr_derivinstr_asst_fx_othr is not None:
                            single_instr_notnl_ccy2 = xml_find_text(xml_tx_new_instr_othr_derivinstr_asst_fx, 'OthrNtnlCcy')
# ----------------------------------------------------------------------------------------

                if xml_tx_new_instr_othr_derivinstr_undr is not None:
                    xml_tx_new_instr_othr_derivinstr_undr_swp = xml_find(xml_tx_new_instr_othr_derivinstr_undr, 'Swp')
                    if xml_tx_new_instr_othr_derivinstr_undr_swp is not None:

                        for i, j in zip(['SwpIn', 'SwpOut'], ['+', '-']):
                            xml_tx_new_instr_othr_derivinstr_undr_swp_inout = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp, i)
                            if xml_tx_new_instr_othr_derivinstr_undr_swp_inout is not None:

# ------------------------------------ Underlying Instrument Code
                                xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout, 'Sngl')
                                xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout, 'Bskt')
                                # for case: sngl
                                if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl is not None:
                                    xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_isin = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl, 'ISIN')
                                    xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl, 'Indx')
                                    if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_isin is not None:
                                        list_instr_under_code.append(str(j)+str(xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl, 'ISIN')))

                                    elif xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx is not None:
                                        xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_isin = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx, 'ISIN')
                                        if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_isin is not None:
                                            list_instr_under_code.append(str(j)+str(xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx, 'ISIN')))
                                # for case: bskt
                                elif xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt is not None:
                                    xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt, 'Indx')
                                    if xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt, 'ISIN') is not None:
                                        isin_bskt = xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt, 'ISIN')
                                        for k in range(len(isin_bskt)):
                                            list_instr_under_code.append(str(j)+str(isin_bskt[k]))

                                    elif xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx is not None:
                                        if xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx, 'ISIN') is not None:
                                            isin_bskt = xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx, 'ISIN')
                                            for k in range(len(isin_bskt)):
                                                list_instr_under_code.append(str(j)+str(isin_bskt[k]))
# ----------------------------------------------------------------------------------------

# ------------------------------------ Underlying Index Name
                                xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout, 'Sngl')
                                xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout, 'Bskt')
                                # for case: sngl
                                if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl is not None:
                                    xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl, 'Indx')
                                    if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx is not None:
                                        xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx, 'Nm')
                                        if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm is not None:
                                            xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_ref = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm, 'RefRate')
                                            if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_ref is not None:
                                                if xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_ref, 'Indx') is not None:
                                                    single_instr_under_name = str(j)+str(xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_ref, 'Indx'))

                                                elif xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_ref, 'Nm') is not None:
                                                    single_instr_under_name = str(j)+str(xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_ref, 'Nm'))
                                # for case: bskt
                                elif xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt is not None:
                                    xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt, 'Indx')
                                    if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx is not None:
                                        xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx, 'Nm')
                                        if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm is not None:
                                            xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_ref = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm, 'Ref')
                                            if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_ref is not None:
                                                if xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_ref, 'Indx') is not None:
                                                    single_instr_under_name = str(j)+str(xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_ref, 'Indx'))

                                                else:
                                                    single_instr_under_name = str(j)+str(xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_ref, 'Nm'))
# ----------------------------------------------------------------------------------------

# ------------------------------------ Term of Underlying Index
                                xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout, 'Sngl')
                                xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout, 'Bskt')
                                # for case: sngl
                                if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl is not None:
                                    xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl, 'Indx')
                                    if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx is not None:
                                        xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx, 'Nm')
                                        if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm is not None:
                                            xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_trm = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm, 'Term')
                                            if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_trm is not None:
                                                if (xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_trm, 'Val') is not None) and \
                                                        (xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_trm, 'Unit') is not None):
                                                    val = xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_trm, 'Val')
                                                    unt = xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_sngl_idx_Nm_trm, 'Unit')
                                                    single_instr_under_term = str(j)+str(val)+' '+str(unt)

                                # for case: bskt
                                elif xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt is not None:
                                    xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt, 'Indx')
                                    if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx is not None:
                                        xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx, 'Nm')
                                        if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm is not None:
                                            xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_trm = xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm, 'Term')
                                            if xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_trm is not None:
                                                if (xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_trm, 'Val') is not None) and \
                                                        (xml_find(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_trm, 'Unit') is not None):
                                                    val = xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_trm, 'Val')
                                                    unt = xml_find_text(xml_tx_new_instr_othr_derivinstr_undr_swp_inout_bskt_idx_Nm_trm, 'Unit')
                                                    single_instr_under_term = str(j)+str(val)+' '+str(unt)
# ----------------------------------------------------------------------------------------

# ------------------------------------ Option Exercise Style, Maturity Date, Expiry Date, Delivery Type
                single_instr_optn_exrc   = xml_find_text(xml_tx_new_instr_othr_derivinstr, 'OptnExrcStyle')
                single_instr_mat_date    = xml_find_text(xml_tx_new_instr_othr_derivinstr, 'MtrtyDt')
                single_instr_exp_date    = xml_find_text(xml_tx_new_instr_othr_derivinstr, 'XpryDt')
                single_instr_dlvry_type  = xml_find_text(xml_tx_new_instr_othr_derivinstr, 'DlvryTp')
# ----------------------------------------------------------------------------------------

    out_row[ind_instr_id_code]     = single_instr_id_code
    out_row[ind_instr_full_name]   = single_instr_full_name
    out_row[ind_instr_class]       = single_instr_class
    out_row[ind_instr_notnl_ccy1]  = single_instr_notnl_ccy1
    out_row[ind_instr_notnl_ccy2]  = single_instr_notnl_ccy2
    out_row[ind_instr_price_mult]  = single_instr_price_mult
    out_row[ind_instr_under_code]  = delim.join(list_instr_under_code)
    out_row[ind_instr_under_name]  = single_instr_under_name
    out_row[ind_instr_under_term]  = single_instr_under_term
    out_row[ind_instr_optn_type]   = single_instr_optn_type
    out_row[ind_instr_strk_type]   = single_instr_strk_type
    out_row[ind_instr_strk_price]  = single_instr_strk_price
    out_row[ind_instr_strk_ccy]    = single_instr_strk_ccy
    out_row[ind_instr_optn_exrc]   = single_instr_optn_exrc
    out_row[ind_instr_mat_date]    = single_instr_mat_date
    out_row[ind_instr_exp_date]    = single_instr_exp_date
    out_row[ind_instr_dlvry_type]  = single_instr_dlvry_type

# ----------------------------- Traders ---------------------------
    single_trade_invst_type  = ''
    single_trade_invst_np    = ''
    single_trade_invst_code  = ''
    single_trade_invst_ctry  = ''
    single_trade_exec_type   = ''
    single_trade_exec_np     = ''
    single_trade_exec_code   = ''
    single_trade_exec_ctry   = ''

    xml_tx_new_invstdcsn = xml_find(xml_tx_new, 'InvstmtDcsnPrsn')

# ----------------------------- Trade Invest Np/Code
    if xml_tx_new_invstdcsn is not None:
        xml_tx_new_invstdcsn_prsn = xml_find(xml_tx_new_invstdcsn, 'Prsn')
        if xml_tx_new_invstdcsn_prsn is not None:
            xml_tx_new_invstdcsn_prsn_othr = xml_find(xml_tx_new_invstdcsn_prsn, 'Othr')
            if xml_tx_new_invstdcsn_prsn_othr is not None:
                if xml_find(xml_tx_new_invstdcsn_prsn_othr, 'Id') is not None:
                    if client_mode == 'NNIP':
                        single_trade_invst_np = xml_find_text(xml_tx_new_invstdcsn_prsn_othr, 'Id')
                    else:
                        single_trade_invst_code = xml_find_text(xml_tx_new_invstdcsn_prsn_othr, 'Id')

        elif xml_find(xml_tx_new_invstdcsn, 'Algo') is not None:
            if client_mode == 'NNIP':
                single_trade_invst_np = xml_find_text(xml_tx_new_invstdcsn, 'Algo')
            else:
                single_trade_invst_code = xml_find_text(xml_tx_new_invstdcsn, 'Algo')
# ----------------------------------------------------------------------------------------

# ----------------------------- Trade Invest Type
        xml_tx_new_invstdcsn_prsn = xml_find(xml_tx_new_invstdcsn, 'Prsn')
        if xml_tx_new_invstdcsn_prsn is not None:
            xml_tx_new_invstdcsn_prsn_othr = xml_find(xml_tx_new_invstdcsn_prsn, 'Othr')
            if xml_tx_new_invstdcsn_prsn_othr is not None:
                xml_tx_new_invstdcsn_prsn_othr_schmenm = xml_find(xml_tx_new_invstdcsn_prsn_othr, 'SchmeNm')
                if xml_find(xml_tx_new_invstdcsn_prsn_othr_schmenm, 'Cd') is not None:
                    if xml_find_text(xml_tx_new_invstdcsn_prsn_othr_schmenm, 'Cd') != 'NIDN':
                        single_trade_invst_type = xml_find_text(xml_tx_new_invstdcsn_prsn_othr_schmenm, 'Cd')
                    else:
                        single_trade_invst_type = 'NIND'

                elif xml_find(xml_tx_new_invstdcsn_prsn_othr_schmenm, 'Prtry') is not None:
                    single_trade_invst_type = xml_find_text(xml_tx_new_invstdcsn_prsn_othr_schmenm, 'Prtry')

        elif xml_find(xml_tx_new_invstdcsn, 'Algo') is not None:
            single_trade_invst_type = 'ALGO'
# ----------------------------------------------------------------------------------------

# ----------------------------- Trade Invest Country of Branch
        xml_tx_new_invstdcsn_prsn = xml_find(xml_tx_new_invstdcsn, 'Prsn')
        if xml_tx_new_invstdcsn_prsn is not None:
            if xml_find(xml_tx_new_invstdcsn_prsn, 'CtryOfBrnch') is not None:
                single_trade_invst_ctry = xml_find_text(xml_tx_new_invstdcsn_prsn, 'CtryOfBrnch')
# ---------------------------------------------------------------------------------------

# ----------------------------- Trade Execution Type
    xml_tx_new_exctprsn = xml_find(xml_tx_new, 'ExctgPrsn')

    if xml_tx_new_exctprsn is not None:
        xml_tx_new_exctprsn_prsn = xml_find(xml_tx_new_exctprsn, 'Prsn')
        if xml_tx_new_exctprsn_prsn is not None:
            xml_tx_new_exctprsn_prsn_othr = xml_find(xml_tx_new_exctprsn_prsn, 'Othr')
            if xml_tx_new_exctprsn_prsn_othr is not None:
                xml_tx_new_exctprsn_prsn_othr_schmenm = xml_find(xml_tx_new_exctprsn_prsn_othr, 'SchmeNm')
                if xml_find(xml_tx_new_exctprsn_prsn_othr_schmenm, 'Cd') is not None:
                    if xml_find_text(xml_tx_new_exctprsn_prsn_othr_schmenm, 'Cd') != 'NIDN':
                        single_trade_exec_type = xml_find_text(xml_tx_new_exctprsn_prsn_othr_schmenm, 'Cd')
                    else:
                        single_trade_exec_type = 'NIND'

                elif xml_find(xml_tx_new_exctprsn_prsn_othr_schmenm, 'Prtry') is not None:
                    single_trade_exec_type = xml_find_text(xml_tx_new_exctprsn_prsn_othr_schmenm, 'Prtry')

        elif xml_find(xml_tx_new_exctprsn, 'Algo') is not None:
            single_trade_exec_type = 'ALGO'

        elif xml_find(xml_tx_new_exctprsn, 'Clnt') is not None:
                single_trade_exec_type = 'CLIENT'
# ----------------------------------------------------------------------------------------

# ----------------------------- Trade Execution Code/np
        xml_tx_new_exctprsn_prsn = xml_find(xml_tx_new_exctprsn, 'Prsn')
        if xml_find(xml_tx_new_exctprsn, 'Prsn') is not None:
            xml_tx_new_exctprsn_prsn_othr = xml_find(xml_tx_new_exctprsn_prsn, 'Othr')
            if xml_tx_new_exctprsn_prsn_othr is not None:
                if xml_find(xml_tx_new_exctprsn_prsn_othr, 'Id') is not None:
                    # NOTE: this is NNIP specific
                    if client_mode == 'NNIP':
                        single_trade_exec_np = xml_find_text(xml_tx_new_exctprsn_prsn_othr, 'Id')
                    else:
                        single_trade_exec_code = xml_find_text(xml_tx_new_exctprsn_prsn_othr, 'Id')

        elif xml_find(xml_tx_new_exctprsn, 'Algo') is not None:
            # NOTE: this is NNIP specific
            if client_mode == 'NNIP':
                single_trade_exec_np = xml_find_text(xml_tx_new_exctprsn, 'Algo')
            else:
                single_trade_exec_code = xml_find_text(xml_tx_new_exctprsn, 'Algo')
# ----------------------------------------------------------------------------------------

# ----------------------------- Trade Country of Branch
        if xml_tx_new_exctprsn_prsn is not None:
            if xml_find(xml_tx_new_exctprsn_prsn, 'CtryOfBrnch') is not None:
                single_trade_exec_ctry = xml_find_text(xml_tx_new_exctprsn_prsn, 'CtryOfBrnch')
# ----------------------------------------------------------------------------------------

# ----------------------------- Waiver and indicator details ---------------------------
    list_trade_waiver_ind    = []
    single_trade_shrt_ind    = ''
    list_trade_post_ind      = []
    single_trade_drv_ind     = ''
    single_trade_sec_ind     = ''

# ----------------------------- Waiver Indicator
    xml_tx_new_addtl = xml_find(xml_tx_new, 'AddtlAttrbts')
    if xml_tx_new_addtl is not None:
        for xml_indic in xml_findall(xml_tx_new_addtl, 'WvrInd'):
            if xml_indic is not None:
                list_trade_waiver_ind.append(xml_indic.text)
# ----------------------------------------------------------------------------------------

# ----------------------------- Short Selling Indicator
        if xml_find(xml_tx_new_addtl, 'ShrtSellgInd') is not None:
            single_trade_shrt_ind = xml_find_text(xml_tx_new_addtl, 'ShrtSellgInd')
# ----------------------------------------------------------------------------------------

# ----------------------------- OTC Post-trade Indicator
        for xml_indic in xml_findall(xml_tx_new_addtl, 'OTCPstTradInd'):
            if xml_indic is not None:
                list_trade_post_ind.append(xml_indic.text)
# ----------------------------------------------------------------------------------------

# ----------------------------- Comodity Derivative Indicator
        xml_tx_new_rskrdcg = xml_find(xml_tx_new_addtl, 'RskRdcgTx')
        if xml_tx_new_rskrdcg is not None:
            if xml_find_text(xml_tx_new_addtl, 'RskRdcgTx') == '1':
                single_trade_drv_ind = 'True'
            elif xml_find_text(xml_tx_new_addtl, 'RskRdcgTx') == '0':
                single_trade_drv_ind = 'False'
            else:
                single_trade_drv_ind = xml_find_text(xml_tx_new_addtl, 'RskRdcgTx')
# ----------------------------------------------------------------------------------------

# ----------------------------- Securities Financing Indicator
        xml_tx_new_addtl_scties = xml_find(xml_tx_new_addtl, 'SctiesFincgTxInd')
        if xml_tx_new_addtl_scties is not None:
            if xml_find_text(xml_tx_new_addtl, 'SctiesFincgTxInd') == '1':
                single_trade_sec_ind = 'True'
            elif xml_find_text(xml_tx_new_addtl, 'SctiesFincgTxInd') == '0':
                single_trade_sec_ind = 'False'
            else:
                single_trade_sec_ind = xml_find_text(xml_tx_new_addtl, 'SctiesFincgTxInd')
# ----------------------------------------------------------------------------------------

    out_row[ind_trade_invst_type]  = single_trade_invst_type
    out_row[ind_trade_invst_np]    = single_trade_invst_np
    out_row[ind_trade_invst_code]  = single_trade_invst_code
    out_row[ind_trade_invst_ctry]  = single_trade_invst_ctry
    out_row[ind_trade_exec_type]   = single_trade_exec_type
    out_row[ind_trade_exec_np]     = single_trade_exec_np
    out_row[ind_trade_exec_code]   = single_trade_exec_code
    out_row[ind_trade_exec_ctry]   = single_trade_exec_ctry
    out_row[ind_trade_waiver_ind]  = delim.join(list_trade_waiver_ind)
    out_row[ind_trade_shrt_ind]    = single_trade_shrt_ind
    out_row[ind_trade_post_ind]    = delim.join(list_trade_post_ind)
    out_row[ind_trade_drv_ind]     = single_trade_drv_ind
    out_row[ind_trade_sec_ind]     = single_trade_sec_ind

    # Eligibility details
    single_elig_branch_loc   = ''
    single_elig_trnsc_type   = ''
    single_elig_cycle_event  = ''

    xml_tx_new_elig = xml_find(xml_tx_new, 'ElgbltyDtrmntnAttrbts')
    if xml_tx_new_elig is not None:
        single_elig_branch_loc   = xml_find_text(xml_tx_new_elig, 'BrnchLctn')
        single_elig_trnsc_type   = xml_find_text(xml_tx_new_elig, 'TxTp')
        single_elig_cycle_event  = xml_find_text(xml_tx_new_elig, 'LfcclEvnt')

    out_row[ind_elig_branch_loc]   = single_elig_branch_loc
    out_row[ind_elig_trnsc_type]   = single_elig_trnsc_type
    out_row[ind_elig_cycle_event]  = single_elig_cycle_event

    return


def get_output_row_cxl(xml_tx_cxl):

    # Report Details
    out_row[ind_report_status]     = 'CANC'
    out_row[ind_trans_ref_no]      = xml_find_text(xml_tx_cxl, 'TxId')
    out_row[ind_trans_id_code]     = ''
    out_row[ind_entity_id_code]    = xml_find_text(xml_tx_cxl, 'ExctgPty')
    out_row[ind_cover_201465eu]    = ''

    # Buyer Details
    out_row[ind_buy_acct_id_type]  = ''
    out_row[ind_buy_acct_np_code]  = ''
    out_row[ind_buy_acct_id_code]  = ''
    out_row[ind_buy_acct_country]  = ''
    out_row[ind_buy_acct_forename] = ''
    out_row[ind_buy_acct_surname]  = ''
    out_row[ind_buy_acct_birthdt]  = ''

    # Buyer Decision Maker details
    out_row[ind_buy_dcsn_id_type]  = ''
    out_row[ind_buy_dcsn_np_code]  = ''
    out_row[ind_buy_dcsn_id_code]  = ''
    out_row[ind_buy_dcsn_forename] = ''
    out_row[ind_buy_dcsn_surname]  = ''
    out_row[ind_buy_dcsn_birthdt]  = ''

    # Seller Details
    out_row[ind_sel_acct_id_type]  = ''
    out_row[ind_sel_acct_np_code]  = ''
    out_row[ind_sel_acct_id_code]  = ''
    out_row[ind_sel_acct_country]  = ''
    out_row[ind_sel_acct_forename] = ''
    out_row[ind_sel_acct_surname]  = ''
    out_row[ind_sel_acct_birthdt]  = ''

    # Seller Decision Maker details
    out_row[ind_sel_dcsn_id_type]  = ''
    out_row[ind_sel_dcsn_np_code]  = ''
    out_row[ind_sel_dcsn_id_code]  = ''
    out_row[ind_sel_dcsn_forename] = ''
    out_row[ind_sel_dcsn_surname]  = ''
    out_row[ind_sel_dcsn_birthdt]  = ''

    # Transmission details
    out_row[ind_trnsm_order_ind]   = ''
    out_row[ind_trnsm_buy_id_code] = ''
    out_row[ind_trnsm_sel_id_code] = ''

    # Transaction details
    out_row[ind_trnsc_datetime]    = ''
    out_row[ind_trnsc_trade_cap]   = ''
    out_row[ind_trnsc_qty_type]    = ''
    out_row[ind_trnsc_qty_val]     = ''
    out_row[ind_trnsc_qty_ccy]     = ''
    out_row[ind_trnsc_drv_notion]  = ''
    out_row[ind_trnsc_prc_type]    = ''
    out_row[ind_trnsc_prc_val]     = ''
    out_row[ind_trnsc_prc_ccy]     = ''
    out_row[ind_trnsc_net_amt]     = ''
    out_row[ind_trnsc_venue]       = ''
    out_row[ind_trnsc_brnch_ctry]  = ''
    out_row[ind_trnsc_up_fr_amt]   = ''
    out_row[ind_trnsc_up_fr_ccy]   = ''
    out_row[ind_trnsc_cmpnt_id]    = ''

    # Instrument details
    out_row[ind_instr_id_code]     = ''
    out_row[ind_instr_full_name]   = ''
    out_row[ind_instr_class]       = ''
    out_row[ind_instr_notnl_ccy1]  = ''
    out_row[ind_instr_notnl_ccy2]  = ''
    out_row[ind_instr_price_mult]  = ''
    out_row[ind_instr_under_code]  = ''
    out_row[ind_instr_under_name]  = ''
    out_row[ind_instr_under_term]  = ''
    out_row[ind_instr_optn_type]   = ''
    out_row[ind_instr_strk_type]   = ''
    out_row[ind_instr_strk_price]  = ''
    out_row[ind_instr_strk_ccy]    = ''
    out_row[ind_instr_optn_exrc]   = ''
    out_row[ind_instr_mat_date]    = ''
    out_row[ind_instr_exp_date]    = ''
    out_row[ind_instr_dlvry_type]  = ''

    # Trading details
    out_row[ind_trade_invst_type]  = ''
    out_row[ind_trade_invst_np]    = ''
    out_row[ind_trade_invst_code]  = ''
    out_row[ind_trade_invst_ctry]  = ''
    out_row[ind_trade_exec_type]   = ''
    out_row[ind_trade_exec_np]     = ''
    out_row[ind_trade_exec_code]   = ''
    out_row[ind_trade_exec_ctry]   = ''
    out_row[ind_trade_waiver_ind]  = ''
    out_row[ind_trade_shrt_ind]    = ''
    out_row[ind_trade_post_ind]    = ''
    out_row[ind_trade_drv_ind]     = ''
    out_row[ind_trade_sec_ind]     = ''

    # Eligibility details
    out_row[ind_elig_branch_loc]   = ''
    out_row[ind_elig_trnsc_type]   = ''
    out_row[ind_elig_cycle_event]  = ''

    return


def output_bad_xml():

    global output_csv_file
    global out_row

    # Slurp in XML file
    with codecs.open(args.in_xml, 'r', 'utf-8') as in_xml_file:
        xml_single_line = ''.join(line.strip() for line in in_xml_file)

    # Write output CSV file
    if output_csv_file is not None:
        output_csv_file.close()

    output_csv_file = codecs.open(args.out_csv, 'w', 'utf-8')
    output_csv_rows = csv.writer(output_csv_file)

    out_row = [''] * number_of_columns
    get_output_header_row()

    output_csv_rows.writerow(out_row)
    out_row = [''] * number_of_columns

    out_row[0] = 'INVALID_XML'
    out_row[1] = xml_single_line

    output_csv_rows.writerow(out_row)
    output_csv_file.close()


# run code specific to the client - read from the configuration table input
client_mode = get_clnt_mode()
mode = 'multi'
counter = 0
print('Client: ', client_mode)
print('Mode: ', mode)

# Set dummy name - this will change later
output_dummy_filename = os.path.join(args.out_csv, "NNIP_Output_File.csv")

# Open output CSV files
output_csv_file = codecs.open(output_dummy_filename, 'w', 'utf-8')
output_csv_rows = csv.writer(output_csv_file)

# Output CSV header row
out_row = [''] * number_of_columns
get_output_header_row()
output_csv_rows.writerow(out_row)

if mode == 'single':

    #  Open & parse a single XML file (getting first <Document> tag
    xml_file = args.in_xml
    xml = ElemTree.parse(xml_file).getroot()
    xml_tag = re.match(r'({.*})Document$', xml.tag)

    # Output CSV header row
    out_row = [''] * number_of_columns
    get_output_header_row()
    output_csv_rows.writerow(out_row)

    if xml_tag is None:
        print('Unrecognised XML!')
        output_bad_xml()
        exit(0)

    xml_namespace_tag = xml_tag[1]
    tx_no = 0
    xml_rpt = xml_find(xml, 'FinInstrmRptgTxRpt')

    for xml_rpt_tx in xml_findall(xml_rpt, 'Tx'):

        tx_no += 1
        out_row = [''] * number_of_columns
        xml_rpt_tx_new = xml_find(xml_rpt_tx, 'New')

        if xml_rpt_tx_new is not None:
            get_output_row_new(xml_rpt_tx_new, xml_file)
        else:
            xml_rpt_tx_cxl = xml_find(xml_rpt_tx, 'Cxl')

            if xml_rpt_tx_cxl is not None:
                get_output_row_cxl(xml_rpt_tx_cxl)
            else:
                print('TX block number ' + str(tx_no) + ' has no NEW or CXL blocks!')
                output_bad_xml()
                exit(0)

        output_csv_rows.writerow(out_row)

# run multiple xml files from a folder
elif mode == 'multi':

    #  Open & parse input XML files
    xml_files = [os.path.join(args.in_xml, f) for f in os.listdir(args.in_xml) if os.path.isfile(os.path.join(args.in_xml, f))]
    for xml_file in xml_files:
        xml = ElemTree.parse(xml_file).getroot()
        xml_tag = re.match(r'({.*})Document$', xml.tag)

        if xml_tag is None:
            print('Unrecognised XML!')
            output_bad_xml()
            exit(0)

        xml_namespace_tag = xml_tag[1]
        tx_no = 0
        xml_rpt = xml_find(xml, 'FinInstrmRptgTxRpt')

        for xml_rpt_tx in xml_findall(xml_rpt, 'Tx'):

            tx_no += 1
            out_row = [''] * number_of_columns
            xml_rpt_tx_new = xml_find(xml_rpt_tx, 'New')

            if xml_rpt_tx_new is not None:
                get_output_row_new(xml_rpt_tx_new, xml_file)
            else:
                xml_rpt_tx_cxl = xml_find(xml_rpt_tx, 'Cxl')

                if xml_rpt_tx_cxl is not None:
                    get_output_row_cxl(xml_rpt_tx_cxl)
                else:
                    print('TX block number ' + str(tx_no) + ' has no NEW or CXL blocks!')
                    output_bad_xml()
                    exit(0)

            output_csv_rows.writerow(out_row)
            counter += 1

print('Number of transactions: ', counter)

# build csv file name format 'LEI_MIFID_yyyymmdd_hhmmss_NNIPOUTPUT_####'
lei_tag = get_tag_content(xml_rpt_tx_new, 'ExctgPty')
year_tag = datetime.datetime.today().strftime('%Y%m%d')
time_tag = datetime.datetime.today().strftime('%H%M%S')

seperator = '_'
tags = (lei_tag, "MIFID_", year_tag, time_tag, "NNIPOUTPUT_0000.csv")
output_filename_tags = seperator.join(tags)
output_filename = os.path.join(args.out_csv, output_filename_tags)

output_csv_file.close()

os.rename(output_dummy_filename, output_filename)














