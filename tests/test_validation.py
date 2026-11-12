import unittest
from app import validate_imei, make_imei

class ImeiValidationTests(unittest.TestCase):
    def test_generated_imei_passes(self):
        imei=make_imei("35678901","123456")
        self.assertEqual(len(imei),15)
        self.assertTrue(validate_imei(imei)[0])
    def test_bad_length_fails(self):
        self.assertFalse(validate_imei("12345")[0])
    def test_bad_check_digit_fails(self):
        imei=make_imei("35678901","123456")
        bad=imei[:-1]+str((int(imei[-1])+1)%10)
        self.assertFalse(validate_imei(bad)[0])

if __name__=="__main__": unittest.main()
