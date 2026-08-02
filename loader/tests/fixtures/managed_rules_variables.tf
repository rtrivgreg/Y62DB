variable "access_keys_rotated_parameters" {
  type = object({
    maxAccessKeyAge = optional(number, 90)
  })
  default = {
    maxAccessKeyAge = 90
  }
}
