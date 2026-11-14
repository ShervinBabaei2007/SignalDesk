// Tests for the summary cleanup.
import { describe, expect, it } from 'vitest'
import { cleanSummary } from '@/lib/text'

describe('cleanSummary', () => {
  it('removes a row of share buttons and the FULL STORY teaser', () => {
    expect(cleanSummary('Their analysis could transform treatments. Facebook Twitter Pinterest LinkedIn Email FULL STORY A major Yale study reveals results.'))
      .toBe('Their analysis could transform treatments. A major Yale study reveals results.')
  })

  it('copes with pages that vary the casing of the share row', () => {
    expect(cleanSummary('Results are mixed. Facebook Twitter Pinterest LinkedIN Email FULL STORY A major study found more.'))
      .toBe('Results are mixed. A major study found more.')
  })

  it('removes stock-photo credits and publication stamps', () => {
    expect(cleanSummary('Credit: Shutterstock A growing body of research suggests that aging may be modifiable.'))
      .toBe('A growing body of research suggests that aging may be modifiable.')
    expect(cleanSummary('The storms have left thousands displaced. Published On 14 Nov 2026 14 Nov 2026 Save'))
      .toBe('The storms have left thousands displaced.')
    expect(cleanSummary('Recommended Stories list of 3 items list 1 of 3 Europe’s ties are fraying.')).toBe('Europe’s ties are fraying.')
  })

  it('leaves real prose alone, including words that are also share-button labels', () => {
    const prose = 'Officials said they would share the email with Facebook and Twitter before the full story was published.'
    expect(cleanSummary(prose)).toBe(prose)
    expect(cleanSummary('The company will print and share updates by email.')).toBe('The company will print and share updates by email.')
  })

  it('copes with empty text and tidies whitespace', () => {
    expect(cleanSummary('')).toBe('')
    expect(cleanSummary('  A   spaced    sentence.  ')).toBe('A spaced sentence.')
  })
})
