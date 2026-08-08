# DS-ACK V1.12 release builds

These packages are built from the `duhan-(4.9.337)` source profile with:

- Exynos9810 targets: G960F, G965F, N960F, G960N, G965N and N960N
- EROFS system, vendor and odm fstab entries
- OneUI brightness workaround
- Google Clang 20

`KernelSU` appears in the filename and embedded config only for the two KernelSU packages.

Build all four packages from the source tree:

```bash
DS_ACK_CLEAN=n bash apollo.sh --all-releases
```
